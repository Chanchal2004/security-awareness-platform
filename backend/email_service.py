
import os
import re
import ipaddress
import logging

import requests

from html.parser import HTMLParser
from urllib.parse import urlparse


logger = logging.getLogger(__name__)


# ============================================================
# POSTMARK CONFIG
# ============================================================

POSTMARK_SERVER_TOKEN = os.environ["POSTMARK_SERVER_TOKEN"]

EMAIL_FROM = os.environ["EMAIL_FROM"]

EMAIL_FROM_NAME = os.environ.get(
    "EMAIL_FROM_NAME",
    "Talbros Security Awareness",
)

EMAIL_REPLY_TO = os.environ.get("EMAIL_REPLY_TO")

POSTMARK_URL = "https://api.postmarkapp.com/email"

MESSAGE_STREAM = os.environ.get(
    "POSTMARK_MESSAGE_STREAM",
    "outbound",
)


# ============================================================
# EMAIL SAFETY VALIDATION
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

    if not host:
        return False

    if "xn--" in host:
        return False

    try:
        ipaddress.ip_address(host)
        return False
    except ValueError:
        pass

    return not any(
        host == shortener
        or host.endswith("." + shortener)
        for shortener in _SHORTENERS
    )


def _same_site(shown: str, real: str) -> bool:

    return (
        shown == real
        or real.endswith("." + shown)
        or shown.endswith("." + real)
    )


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


def assert_safe_email(
    subject: str,
    html: str,
) -> None:

    scan = _EmailScan()

    scan.feed(html)

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

    body = f"{subject}\n{html}".lower()

    for phrase in _CRED_ASK:

        if phrase in body:

            raise ValueError(
                "Email may not ask recipients for "
                "passwords or credentials."
            )

    for url in scan.urls:

        low = url.strip().lower()

        if low.startswith(
            (
                "mailto:",
                "tel:",
                "cid:",
                "#",
            )
        ):
            continue

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

        if (
            not _host_ok(host)
            or parsed.username is not None
            or parsed.password is not None
        ):

            raise ValueError(
                "Shortened, numeric-host or "
                "credential-bearing URLs are not allowed."
            )

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
# SEND EMAIL WITH POSTMARK
# ============================================================

async def send_email(
    *,
    to: str,
    subject: str,
    html: str,
    reply_to: str | None = None,
) -> str | None:

    assert_safe_email(
        subject,
        html,
    )

    from_address = (
        f"{EMAIL_FROM_NAME} <{EMAIL_FROM}>"
    )

    payload = {
        "From": from_address,
        "To": to,
        "Subject": subject,
        "HtmlBody": html,
        "MessageStream": MESSAGE_STREAM,
    }

    final_reply_to = (
        reply_to
        or EMAIL_REPLY_TO
    )

    if final_reply_to:

        payload["ReplyTo"] = final_reply_to

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Postmark-Server-Token": POSTMARK_SERVER_TOKEN,
    }

    try:

        response = requests.post(
            POSTMARK_URL,
            headers=headers,
            json=payload,
            timeout=30,
        )

        if not response.ok:

            logger.error(
                "Postmark email failed for %s: %s %s",
                to,
                response.status_code,
                response.text,
            )

            response.raise_for_status()

        data = response.json()

        message_id = data.get("MessageID")

        logger.info(
            "Email sent successfully to %s via Postmark "
            "(MessageID=%s)",
            to,
            message_id,
        )

        return message_id

    except Exception:

        logger.exception(
            "Postmark API send failed for %s",
            to,
        )

        raise
