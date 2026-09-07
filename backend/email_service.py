import os
import re
import ipaddress
import logging

import requests

from html.parser import HTMLParser
from urllib.parse import urlparse


logger = logging.getLogger(__name__)


# ============================================================
# Brevo configuration
# ============================================================

BREVO_API_KEY = os.environ["BREVO_API_KEY"]
EMAIL_FROM_NAME = os.environ["EMAIL_FROM_NAME"]
EMAIL_REPLY_TO = os.environ.get("EMAIL_REPLY_TO")


# ============================================================
# Safety rules
# ============================================================

_SHORTENERS = (
    "bit.ly",
    "tinyurl.com",
    "t.co",
    "is.gd",
    "cutt.ly",
    "goo.gl",
    "rebrand.ly",
)

_CRED_ASK = (
    "reply with your password",
    "reply with the code",
    "send your password",
    "cvv",
    "send us your password",
    "enter your password below",
    "confirm your card number",
    "your full card number",
    "seed phrase",
    "recovery phrase",
    "verify your card",
    "social security number",
    "confirm your bank details",
)

_HOSTISH = re.compile(
    r"\b(?:https?://)?((?:[a-z0-9-]+\.)+[a-z]{2,})",
    re.I,
)


def _host_ok(host: str) -> bool:
    if not host or "xn--" in host:
        return False

    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass

    return not any(
        host == s or host.endswith("." + s)
        for s in _SHORTENERS
    )


def _same_site(shown: str, real: str) -> bool:
    return (
        shown == real
        or real.endswith("." + shown)
        or shown.endswith("." + real)
    )


# ============================================================
# HTML scanner
# ============================================================

class _EmailScan(HTMLParser):

    def __init__(self):
        super().__init__()

        self.tags = set()
        self.urls = []
        self.anchors = []

        self._href = None
        self._text = []

    def handle_starttag(self, tag, attrs):
        self.tags.add(tag.lower())

        self.urls += [
            value
            for key, value in attrs
            if key.lower() in ("href", "src") and value
        ]

        if tag.lower() == "a":
            self._href = dict(
                (key.lower(), value)
                for key, value in attrs
            ).get("href")

            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.anchors.append(
                (
                    self._href,
                    "".join(self._text),
                )
            )

            self._href = None
            self._text = []


# ============================================================
# Email safety validation
# ============================================================

def assert_safe_email(subject: str, html: str) -> None:
    """
    Validate email content before delivery.

    Emails cannot contain:
    - credential-collection forms
    - password requests
    - unsafe URLs
    - misleading links

    Localhost HTTP URLs are allowed for local development/testing.
    Production tracking should use publicly reachable HTTPS URLs.
    """

    scan = _EmailScan()
    scan.feed(html)

    # --------------------------------------------------------
    # No forms/input fields in email templates
    # --------------------------------------------------------

    if scan.tags & {
        "form",
        "input",
        "textarea",
        "select",
    }:
        raise ValueError(
            "Email templates may not contain forms or input fields."
        )

    body = f"{subject}\n{html}".lower()

    # --------------------------------------------------------
    # No credential requests
    # --------------------------------------------------------

    for phrase in _CRED_ASK:
        if phrase in body:
            raise ValueError(
                "Email may not ask recipients for passwords or credentials."
            )

    # --------------------------------------------------------
    # Validate URLs
    # --------------------------------------------------------

    for url in scan.urls:

        low = url.strip().lower()

        # Safe non-web URLs
        if low.startswith(
            (
                "mailto:",
                "tel:",
                "cid:",
                "#",
            )
        ):
            continue

        # ----------------------------------------------------
        # HTTPS URLs are allowed.
        #
        # localhost / 127.0.0.1 are allowed for local testing.
        # ----------------------------------------------------

        if not low.startswith(
            (
                "https://",
                "http://localhost:",
                "http://127.0.0.1:",
            )
        ):
            raise ValueError(
                "All email links and images must be absolute https URLs."
            )

        parsed = urlparse(low)

        host = parsed.hostname or ""

        if not _host_ok(host) or parsed.username is not None:
            raise ValueError(
                "Shortened, numeric-host or credential-bearing URLs are not allowed."
            )

    # --------------------------------------------------------
    # Validate visible link text vs actual destination
    # --------------------------------------------------------

    for href, text in scan.anchors:

        real = (
            urlparse(
                href.strip().lower()
            ).hostname
            or ""
        )

        if not real:
            continue

        for match in _HOSTISH.finditer(text):

            shown = match.group(1).lower()

            if not _same_site(shown, real):
                raise ValueError(
                    "Link text must not reference a different website "
                    "than the link target."
                )


# ============================================================
# Send email using Brevo API
# ============================================================

async def send_email(
    *,
    to: str,
    subject: str,
    html: str,
    reply_to: str | None = None,
) -> str | None:

    """
    Send an authorized email through Brevo API.

    Sender identity is controlled by EMAIL_FROM_NAME.
    """

    # --------------------------------------------------------
    # Safety validation
    # --------------------------------------------------------

    assert_safe_email(
        subject,
        html,
    )

    # --------------------------------------------------------
    # Brevo API payload
    # --------------------------------------------------------

    payload = {
        "sender": {
            "email": EMAIL_FROM_NAME,
        },
        "to": [
            {
                "email": to,
            }
        ],
        "subject": subject,
        "htmlContent": html,
    }

    # --------------------------------------------------------
    # Optional Reply-To
    # --------------------------------------------------------

    final_reply_to = (
        reply_to
        or EMAIL_REPLY_TO
    )

    if final_reply_to:
        payload["replyTo"] = {
            "email": final_reply_to,
        }

    # --------------------------------------------------------
    # Brevo API request
    # --------------------------------------------------------

    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json",
    }

    try:

        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            headers=headers,
            json=payload,
            timeout=30,
        )

        # ----------------------------------------------------
        # Check Brevo response
        # ----------------------------------------------------

        if not response.ok:
            logger.error(
                "Brevo email failed for %s: %s %s",
                to,
                response.status_code,
                response.text,
            )

            response.raise_for_status()

        data = response.json()

        message_id = data.get("messageId")

        logger.info(
            "Email sent successfully to %s via Brevo",
            to,
        )

        return message_id

    except Exception:
        logger.exception(
            "Brevo API send failed for %s",
            to,
        )
        raise
