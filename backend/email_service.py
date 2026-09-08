import os
import re
import ipaddress
import logging

import requests

from html.parser import HTMLParser
from urllib.parse import urlparse


logger = logging.getLogger(__name__)


# ============================================================
# MailerSend configuration
# ============================================================

MAILERSEND_API_TOKEN = os.environ["MAILERSEND_API_TOKEN"]

# IMPORTANT:
# This MUST be an email address belonging to a VERIFIED
# MailerSend sending domain.
#
# Example:
# EMAIL_FROM=security@test-xkjn41modd64z781.mlsender.net
#
# DO NOT use your Gmail address here unless that domain
# is actually verified by MailerSend.
EMAIL_FROM = os.environ["EMAIL_FROM"]

# Display name shown to the recipient.
EMAIL_FROM_NAME = os.environ.get(
    "EMAIL_FROM_NAME",
    "Talbros Security Awareness",
)

# Optional Reply-To address.
EMAIL_REPLY_TO = os.environ.get("EMAIL_REPLY_TO")


# ============================================================
# Safe API-key diagnostic
# ============================================================

# NEVER print the complete API token.
logger.info(
    "MailerSend configuration loaded: token_prefix=%s token_length=%d from=%s",
    MAILERSEND_API_TOKEN[:8],
    len(MAILERSEND_API_TOKEN),
    EMAIL_FROM,
)


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
    """
    Return True when a URL host is acceptable.
    """

    if not host:
        return False

    # Reject internationalized/punycode hosts.
    if "xn--" in host:
        return False

    # Reject numeric IP addresses.
    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass

    # Reject known URL shorteners.
    return not any(
        host == shortener
        or host.endswith("." + shortener)
        for shortener in _SHORTENERS
    )


def _same_site(shown: str, real: str) -> bool:
    """
    Check whether visible link text and actual destination
    refer to the same site.
    """

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
        tag_lower = tag.lower()

        self.tags.add(tag_lower)

        for key, value in attrs:
            if (
                key.lower() in ("href", "src")
                and value
            ):
                self.urls.append(value)

        if tag_lower == "a":
            attributes = {
                key.lower(): value
                for key, value in attrs
            }

            self._href = attributes.get("href")
            self._text = []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if (
            tag.lower() == "a"
            and self._href is not None
        ):
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

def assert_safe_email(
    subject: str,
    html: str,
) -> None:
    """
    Validate email content before delivery.

    Emails cannot contain:

    - credential-collection forms
    - password requests
    - unsafe URLs
    - misleading links

    Localhost HTTP URLs are allowed for local
    development/testing.
    """

    scan = _EmailScan()
    scan.feed(html)

    # --------------------------------------------------------
    # No forms/input fields in email templates
    # --------------------------------------------------------

    forbidden_tags = {
        "form",
        "input",
        "textarea",
        "select",
    }

    if scan.tags & forbidden_tags:
        raise ValueError(
            "Email templates may not contain forms "
            "or input fields."
        )

    body = (
        f"{subject}\n{html}"
    ).lower()

    # --------------------------------------------------------
    # No credential requests
    # --------------------------------------------------------

    for phrase in _CRED_ASK:

        if phrase in body:
            raise ValueError(
                "Email may not ask recipients for "
                "passwords or credentials."
            )

    # --------------------------------------------------------
    # Validate URLs
    # --------------------------------------------------------

    for url in scan.urls:

        low = url.strip().lower()

        # Safe non-web URLs.
        if low.startswith(
            (
                "mailto:",
                "tel:",
                "cid:",
                "#",
            )
        ):
            continue

        # HTTPS URLs are allowed.
        #
        # localhost / 127.0.0.1 are allowed only for
        # local development/testing.
        if not low.startswith(
            (
                "https://",
                "http://localhost:",
                "http://127.0.0.1:",
            )
        ):
            raise ValueError(
                "All email links and images must be "
                "absolute https URLs."
            )

        parsed = urlparse(low)

        host = parsed.hostname or ""

        # Reject:
        # - shortened URLs
        # - numeric hosts
        # - credential-bearing URLs
        if (
            not _host_ok(host)
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError(
                "Shortened, numeric-host or "
                "credential-bearing URLs are not allowed."
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

            if not _same_site(
                shown,
                real,
            ):
                raise ValueError(
                    "Link text must not reference a "
                    "different website than the link target."
                )


# ============================================================
# Send email using MailerSend API
# ============================================================

async def send_email(
    *,
    to: str,
    subject: str,
    html: str,
    reply_to: str | None = None,
) -> str | None:
    """
    Send an authorized email through MailerSend API.

    EMAIL_FROM
        Actual sender email address belonging to a
        verified MailerSend domain.

    EMAIL_FROM_NAME
        Display name shown to recipient.

    EMAIL_REPLY_TO
        Optional reply-to address.
    """

    # --------------------------------------------------------
    # Safety validation
    # --------------------------------------------------------

    assert_safe_email(
        subject,
        html,
    )

    # --------------------------------------------------------
    # MailerSend API payload
    # --------------------------------------------------------

    payload = {
        "from": {
            "email": EMAIL_FROM,
            "name": EMAIL_FROM_NAME,
        },
        "to": [
            {
                "email": to,
            }
        ],
        "subject": subject,
        "html": html,
    }

    # --------------------------------------------------------
    # Optional Reply-To
    # --------------------------------------------------------

    final_reply_to = (
        reply_to
        or EMAIL_REPLY_TO
    )

    if final_reply_to:
        payload["reply_to"] = [
            {
                "email": final_reply_to,
            }
        ]

    # --------------------------------------------------------
    # MailerSend API headers
    # --------------------------------------------------------

    headers = {
        "Authorization": f"Bearer {MAILERSEND_API_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    # --------------------------------------------------------
    # MailerSend API request
    # --------------------------------------------------------

    try:

        response = requests.post(
            "https://api.mailersend.com/v1/email",
            headers=headers,
            json=payload,
            timeout=30,
        )

        # ----------------------------------------------------
        # Check MailerSend response
        # ----------------------------------------------------

        if not response.ok:

            logger.error(
                "MailerSend email failed for %s: %s %s",
                to,
                response.status_code,
                response.text,
            )

            response.raise_for_status()

        # ----------------------------------------------------
        # MailerSend normally returns 202 Accepted.
        # The response may not contain JSON/messageId.
        # ----------------------------------------------------

        message_id = response.headers.get(
            "x-message-id"
        )

        logger.info(
            "Email sent successfully to %s via MailerSend",
            to,
        )

        return message_id

    except Exception:

        logger.exception(
            "MailerSend API send failed for %s",
            to,
        )

        raise
