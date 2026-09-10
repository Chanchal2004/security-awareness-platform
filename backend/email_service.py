import os
import re
import ipaddress
import logging
import json
import base64

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from html.parser import HTMLParser
from urllib.parse import urlparse

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


logger = logging.getLogger(__name__)


# ============================================================
# GMAIL API CONFIG
# ============================================================

GMAIL_TOKEN_JSON = os.environ.get("GMAIL_TOKEN_JSON")

EMAIL_FROM_NAME = os.environ.get(
    "EMAIL_FROM_NAME",
    "Talbros Security Awareness",
)

EMAIL_REPLY_TO = os.environ.get("EMAIL_REPLY_TO")

# SEND + READ INCOMING REPLIES / ATTACHMENTS
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
]


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
# GMAIL SERVICE
# ============================================================

def _get_gmail_service():

    if not GMAIL_TOKEN_JSON:

        raise RuntimeError(
            "GMAIL_TOKEN_JSON is not set in Render Environment Variables."
        )

    try:

        token_data = json.loads(
            GMAIL_TOKEN_JSON
        )

    except json.JSONDecodeError as exc:

        raise RuntimeError(
            f"GMAIL_TOKEN_JSON is not valid JSON: {exc}"
        ) from exc

    try:

        credentials = Credentials.from_authorized_user_info(
            token_data,
            GMAIL_SCOPES,
        )

    except Exception as exc:

        raise RuntimeError(
            f"Could not load Gmail credentials from "
            f"GMAIL_TOKEN_JSON: {exc}"
        ) from exc

    # --------------------------------------------------------
    # Refresh expired access token
    # --------------------------------------------------------

    if (
        credentials.expired
        and credentials.refresh_token
    ):

        try:

            credentials.refresh(
                Request()
            )

            logger.info(
                "Gmail access token refreshed successfully."
            )

        except Exception as exc:

            logger.exception(
                "Gmail token refresh failed."
            )

            raise RuntimeError(
                f"Gmail token refresh failed: {exc}"
            ) from exc

    if not credentials.valid:

        raise RuntimeError(
            "Gmail credentials are invalid or expired."
        )

    service = build(
        "gmail",
        "v1",
        credentials=credentials,
        cache_discovery=False,
    )

    return service


# ============================================================
# GET AUTHENTICATED GMAIL ACCOUNT
# ============================================================

async def get_gmail_account_email() -> str:

    gmail_service = _get_gmail_service()

    profile = (
        gmail_service
        .users()
        .getProfile(userId="me")
        .execute()
    )

    email_address = profile.get("emailAddress")

    if not email_address:

        raise RuntimeError(
            "Could not determine authenticated Gmail account."
        )

    return email_address


# ============================================================
# SEND EMAIL WITH GMAIL API
# ============================================================

async def send_email(
    *,
    to: str,
    subject: str,
    html: str,
    reply_to: str | None = None,
) -> dict:

    assert_safe_email(
        subject,
        html,
    )

    final_reply_to = (
        reply_to
        or EMAIL_REPLY_TO
    )

    try:

        message = MIMEMultipart(
            "alternative"
        )

        gmail_service = _get_gmail_service()

        message["To"] = to

        # Always send from the authenticated Gmail account.
        # No user-editable "From" address is accepted.
        sender_email = (
            gmail_service.users()
            .getProfile(userId="me")
            .execute()
            .get("emailAddress")
        )

        if not sender_email:
            raise RuntimeError(
                "Could not determine authenticated Gmail sender."
            )

        message["From"] = f"{EMAIL_FROM_NAME} <{sender_email}>"

        message["Subject"] = subject

        if final_reply_to:

            message["Reply-To"] = (
                final_reply_to
            )

        html_part = MIMEText(
            html,
            "html",
            "utf-8",
        )

        message.attach(
            html_part
        )

        raw_message = (
            base64.urlsafe_b64encode(
                message.as_bytes()
            )
            .decode()
        )

        result = (
            gmail_service
            .users()
            .messages()
            .send(
                userId="me",
                body={
                    "raw": raw_message
                },
            )
            .execute()
        )

        message_id = result.get(
            "id"
        )

        logger.info(
            "Email sent successfully to %s via Gmail API "
            "(MessageID=%s)",
            to,
            message_id,
        )

        # IMPORTANT:
        # Return both Gmail message ID and thread ID.
        # Backend uses thread_id to detect employee replies.
        return {
            "id": message_id,
            "thread_id": result.get("threadId"),
        }

    except Exception:

        logger.exception(
            "Gmail API send failed for %s",
            to,
        )

        raise


# ============================================================
# FIND INCOMING REPLIES
# ============================================================

async def find_incoming_replies(
    *,
    after_message_id: str | None = None,
    max_results: int = 50,
) -> list[dict]:

    gmail_service = _get_gmail_service()

    try:

        result = (
            gmail_service
            .users()
            .messages()
            .list(
                userId="me",
                labelIds=["INBOX"],
                maxResults=max_results,
            )
            .execute()
        )

        messages = result.get(
            "messages",
            []
        )

        output = []

        for item in messages:

            message_id = item.get("id")

            if not message_id:
                continue

            # Fetch complete message
            message = (
                gmail_service
                .users()
                .messages()
                .get(
                    userId="me",
                    id=message_id,
                    format="full",
                )
                .execute()
            )

            payload = message.get(
                "payload",
                {}
            )

            headers = {
                h.get("name", "").lower():
                h.get("value", "")
                for h in payload.get(
                    "headers",
                    []
                )
            }

            output.append(
                {
                    "id": message_id,
                    "thread_id": message.get(
                        "threadId"
                    ),
                    "from": headers.get(
                        "from",
                        ""
                    ),
                    "to": headers.get(
                        "to",
                        ""
                    ),
                    "subject": headers.get(
                        "subject",
                        ""
                    ),
                    "date": headers.get(
                        "date",
                        ""
                    ),
                    "payload": payload,
                }
            )

        return output

    except Exception:

        logger.exception(
            "Failed to read incoming Gmail messages."
        )

        raise


# ============================================================
# EXTRACT MESSAGE TEXT
# ============================================================

def _decode_gmail_body(data: str | None) -> str:

    if not data:
        return ""

    try:

        decoded = base64.urlsafe_b64decode(
            data + "=" * (
                -len(data) % 4
            )
        )

        return decoded.decode(
            "utf-8",
            errors="replace",
        )

    except Exception:

        logger.exception(
            "Could not decode Gmail message body."
        )

        return ""


def extract_message_text(
    payload: dict,
) -> str:

    plain_text = []
    html_text = []

    def walk(part: dict):

        mime_type = part.get(
            "mimeType",
            ""
        )

        body = part.get(
            "body",
            {}
        )

        data = body.get(
            "data"
        )

        if data:

            decoded = _decode_gmail_body(
                data
            )

            if mime_type == "text/plain":

                plain_text.append(
                    decoded
                )

            elif mime_type == "text/html":

                html_text.append(
                    decoded
                )

        for child in part.get(
            "parts",
            []
        ):

            walk(child)

    walk(payload)

    if plain_text:

        return "\n".join(
            plain_text
        ).strip()

    return "\n".join(
        html_text
    ).strip()


# ============================================================
# EXTRACT ATTACHMENTS
# ============================================================

def _collect_attachment_parts(
    payload: dict,
) -> list[dict]:

    attachments = []

    def walk(part: dict):

        filename = part.get(
            "filename"
        )

        body = part.get(
            "body",
            {}
        )

        attachment_id = body.get(
            "attachmentId"
        )

        mime_type = part.get(
            "mimeType",
            "application/octet-stream"
        )

        if filename and attachment_id:

            attachments.append(
                {
                    "filename": filename,
                    "mime_type": mime_type,
                    "attachment_id": attachment_id,
                }
            )

        for child in part.get(
            "parts",
            []
        ):

            walk(child)

    walk(payload)

    return attachments


async def get_message_attachments(
    message_id: str,
    payload: dict,
) -> list[dict]:

    gmail_service = _get_gmail_service()

    parts = _collect_attachment_parts(
        payload
    )

    results = []

    for part in parts:

        try:

            result = (
                gmail_service
                .users()
                .messages()
                .attachments()
                .get(
                    userId="me",
                    messageId=message_id,
                    id=part["attachment_id"],
                )
                .execute()
            )

            encoded_data = result.get(
                "data",
                ""
            )

            file_data = base64.urlsafe_b64decode(
                encoded_data + "=" * (
                    -len(encoded_data) % 4
                )
            )

            results.append(
                {
                    "filename": part["filename"],
                    "mime_type": part["mime_type"],
                    "data": file_data,
                    "size": len(file_data),
                }
            )

        except Exception:

            logger.exception(
                "Failed to download attachment %s "
                "from Gmail message %s",
                part["filename"],
                message_id,
            )

    return results


# ============================================================
# GET REPLY + ATTACHMENTS TOGETHER
# ============================================================

async def get_incoming_message_details(
    message_id: str,
) -> dict:

    gmail_service = _get_gmail_service()

    message = (
        gmail_service
        .users()
        .messages()
        .get(
            userId="me",
            id=message_id,
            format="full",
        )
        .execute()
    )

    payload = message.get(
        "payload",
        {}
    )

    headers = {
        h.get("name", "").lower():
        h.get("value", "")
        for h in payload.get(
            "headers",
            []
        )
    }

    reply_text = extract_message_text(
        payload
    )

    attachments = await get_message_attachments(
        message_id,
        payload,
    )

    return {
        "message_id": message_id,
        "thread_id": message.get(
            "threadId"
        ),
        "from": headers.get(
            "from",
            ""
        ),
        "to": headers.get(
            "to",
            ""
        ),
        "subject": headers.get(
            "subject",
            ""
        ),
        "date": headers.get(
            "date",
            ""
        ),
        "reply_text": reply_text,
        "attachments": attachments,
    }
