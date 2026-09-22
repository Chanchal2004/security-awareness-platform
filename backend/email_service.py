import os
import re
import ipaddress
import logging
import json
import base64
import asyncio
import imaplib
from email import policy
from email.parser import BytesParser
from email.utils import parseaddr, parsedate_to_datetime
from email.header import decode_header, make_header

import msal
import httpx

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
# MICROSOFT GRAPH SEND CONFIG
# ============================================================

MICROSOFT_CLIENT_ID = os.environ.get("MICROSOFT_CLIENT_ID")
MICROSOFT_TENANT_ID = os.environ.get("MICROSOFT_TENANT_ID")
MICROSOFT_AUTHORITY = os.environ.get(
    "MICROSOFT_AUTHORITY",
    "https://login.microsoftonline.com/common",
)
MICROSOFT_SENDER_EMAIL = os.environ.get(
    "MICROSOFT_SENDER_EMAIL",
    "chanchal@qhtalbros.com",
)
MICROSOFT_TOKEN_CACHE = os.environ.get("MICROSOFT_TOKEN_CACHE")
MICROSOFT_SCOPES = ["Mail.Send", "Mail.ReadWrite"]


# ============================================================
# ZOHO IMAP INCOMING REPLY CONFIG
# ============================================================
# Incoming mail for qhtalbros.com is being delivered to Zoho.
# We therefore read replies/attachments from the Zoho mailbox via IMAP.
# Microsoft Graph remains the outbound sender.

ZOHO_IMAP_HOST = os.environ.get("ZOHO_IMAP_HOST", "imap.zoho.com")
ZOHO_IMAP_PORT = int(os.environ.get("ZOHO_IMAP_PORT", "993"))
ZOHO_IMAP_EMAIL = os.environ.get("ZOHO_IMAP_EMAIL", "").strip().replace("\\@", "@").replace("\n", "")
ZOHO_IMAP_PASSWORD = os.environ.get("ZOHO_IMAP_PASSWORD", "")
ZOHO_IMAP_FOLDER = os.environ.get("ZOHO_IMAP_FOLDER", "INBOX")

# When Zoho IMAP is configured, force replies to the same Zoho mailbox.
# Otherwise fall back to EMAIL_REPLY_TO / Microsoft sender.
INBOUND_REPLY_EMAIL = (
    ZOHO_IMAP_EMAIL
    or EMAIL_REPLY_TO
    or MICROSOFT_SENDER_EMAIL
)


# Keep the MSAL cache in memory for the lifetime of the Render process.
# The initial serialized cache is supplied through Render Environment Variables.
_microsoft_token_cache = None
_microsoft_msal_app = None


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
# MICROSOFT GRAPH TOKEN / CLIENT
# ============================================================

def _get_microsoft_msal_app():
    global _microsoft_token_cache, _microsoft_msal_app

    if _microsoft_msal_app is not None:
        return _microsoft_msal_app

    if not MICROSOFT_CLIENT_ID:
        raise RuntimeError(
            "MICROSOFT_CLIENT_ID is not set in Render Environment Variables."
        )

    if not MICROSOFT_TOKEN_CACHE:
        raise RuntimeError(
            "MICROSOFT_TOKEN_CACHE is not set in Render Environment Variables. "
            "Put the serialized MSAL token cache here; do not put only an access token."
        )

    _microsoft_token_cache = msal.SerializableTokenCache()

    try:
        _microsoft_token_cache.deserialize(MICROSOFT_TOKEN_CACHE)
    except Exception as exc:
        raise RuntimeError(
            f"MICROSOFT_TOKEN_CACHE is not a valid MSAL token cache: {exc}"
        ) from exc

    _microsoft_msal_app = msal.PublicClientApplication(
        client_id=MICROSOFT_CLIENT_ID,
        authority=MICROSOFT_AUTHORITY,
        token_cache=_microsoft_token_cache,
    )

    return _microsoft_msal_app


def _get_microsoft_access_token() -> str:
    app = _get_microsoft_msal_app()

    accounts = app.get_accounts(username=MICROSOFT_SENDER_EMAIL)

    if not accounts:
        raise RuntimeError(
            "No Microsoft login account was found in MICROSOFT_TOKEN_CACHE. "
            "Run the local Microsoft login/token-cache generator again and copy the "
            "complete MSAL cache JSON into Render."
        )

    result = app.acquire_token_silent(
        MICROSOFT_SCOPES,
        account=accounts[0],
    )

    if not result or "access_token" not in result:
        error = (result or {}).get("error_description") or (result or {}).get("error")
        raise RuntimeError(
            "Microsoft token acquisition failed."
            + (f" {error}" if error else "")
        )

    logger.info(
        "Microsoft Graph access token acquired successfully for %s.",
        MICROSOFT_SENDER_EMAIL,
    )
    return result["access_token"]


# ============================================================
# SEND EMAIL WITH MICROSOFT GRAPH API
# ============================================================

async def send_email(
    *,
    to: str,
    subject: str,
    html: str,
    reply_to: str | None = None,
) -> dict:
    """Create and send a Microsoft Graph message and return its IDs."""
    assert_safe_email(subject, html)
    final_reply_to = INBOUND_REPLY_EMAIL if ZOHO_IMAP_EMAIL else (reply_to or EMAIL_REPLY_TO or MICROSOFT_SENDER_EMAIL)
    access_token = _get_microsoft_access_token()

    message = {
        "subject": subject,
        "body": {"contentType": "HTML", "content": html},
        "toRecipients": [{"emailAddress": {"address": to}}],
    }
    if final_reply_to:
        message["replyTo"] = [{"emailAddress": {"address": final_reply_to}}]

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Create a draft first so Graph gives us the message/conversation IDs.
        create_response = await client.post(
            "https://graph.microsoft.com/v1.0/me/messages",
            headers=headers,
            json=message,
        )
        if create_response.status_code not in (200, 201):
            try:
                detail = create_response.json()
            except Exception:
                detail = create_response.text
            raise RuntimeError(
                f"Microsoft Graph draft creation failed (HTTP {create_response.status_code}): {detail}"
            )

        created = create_response.json()
        message_id = created.get("id")
        conversation_id = created.get("conversationId")
        internet_message_id = created.get("internetMessageId")
        if not message_id:
            raise RuntimeError("Microsoft Graph did not return a message ID.")

        send_response = await client.post(
            f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/send",
            headers=headers,
        )
        if send_response.status_code != 202:
            try:
                detail = send_response.json()
            except Exception:
                detail = send_response.text
            raise RuntimeError(
                f"Microsoft Graph send failed (HTTP {send_response.status_code}): {detail}"
            )

    logger.info(
        "Email sent via Microsoft Graph to %s from %s (message=%s, conversation=%s)",
        to, MICROSOFT_SENDER_EMAIL, message_id, conversation_id,
    )
    return {
        "id": message_id,
        "thread_id": conversation_id,
        "internet_message_id": internet_message_id,
    }


# ============================================================
# MICROSOFT GRAPH INCOMING REPLIES / ATTACHMENTS
# ============================================================

class _HTMLTextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        value = (data or "").strip()
        if value:
            self.parts.append(value)


def _html_to_text(value: str) -> str:
    if not value:
        return ""
    parser = _HTMLTextParser()
    parser.feed(value)
    parser.close()
    return "\n".join(parser.parts).strip()


def _graph_headers(access_token: str) -> dict:
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }


def _normalize_email_address(value: str) -> str:
    """Normalize email values coming from Graph/env, including escaped @."""
    value = (value or "").strip().strip("<>").strip()
    # Some Render/env copy-pastes can contain a literal backslash before @.
    value = value.replace("\\@", "@")
    return value.lower()


def _graph_address(item: dict) -> str:
    return (
        ((item or {}).get("emailAddress") or {}).get("address")
        or ""
    ).strip()


class _ReplyScan(list):
    """List-compatible scan result used by server.py."""

    def __init__(self, iterable=(), history_id=None):
        super().__init__(iterable)
        self.history_id = history_id

    def get(self, key, default=None):
        if key == "messages":
            return list(self)
        if key == "history_id":
            return self.history_id
        return default


def _zoho_ready() -> bool:
    return bool(ZOHO_IMAP_EMAIL and ZOHO_IMAP_PASSWORD)


def _decode_mime_header(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _iso_date(value: str | None) -> str:
    if not value:
        return ""
    try:
        dt = parsedate_to_datetime(value)
        if dt is None:
            return ""
        return dt.isoformat()
    except Exception:
        return value


def _clean_zoho_password(value: str) -> str:
    """Normalize an app password copied from Zoho/Render."""
    value = (value or "").strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    # Zoho app passwords are not supposed to contain spaces. Removing whitespace
    # also protects IMAP LOGIN from accidental newlines when pasted into Render.
    return "".join(value.split())


def _zoho_hosts() -> list[str]:
    configured = (ZOHO_IMAP_HOST or "imap.zoho.com").strip()
    # Keep the configured host first. For Zoho organization mailboxes, the
    # specialized IMAP endpoint is also commonly supported.
    candidates = [
        configured,
        "imappro.zoho.com",
        "imap.zoho.com",
    ]
    result: list[str] = []
    for host in candidates:
        if host and host not in result:
            result.append(host)
    return result


def _zoho_open() -> imaplib.IMAP4_SSL:
    """Open the Zoho IMAP inbox with a Zoho app password."""
    email_value = (ZOHO_IMAP_EMAIL or "").strip().replace("\\@", "@")
    password_value = _clean_zoho_password(ZOHO_IMAP_PASSWORD)

    if not email_value or not password_value:
        raise RuntimeError(
            "Zoho IMAP is not configured. Set ZOHO_IMAP_EMAIL and "
            "ZOHO_IMAP_PASSWORD (Zoho App Password) in Render Environment Variables."
        )

    last_error = None

    for host in _zoho_hosts():
        mailbox = None
        try:
            logger.info("Connecting to Zoho IMAP host %s as %s.", host, email_value)
            mailbox = imaplib.IMAP4_SSL(
                host,
                ZOHO_IMAP_PORT,
                timeout=20,
            )
            status, data = mailbox.login(email_value, password_value)

            if status != "OK":
                raise RuntimeError(f"Zoho IMAP login failed on {host}: {data!r}")

            status, _ = mailbox.select(
                ZOHO_IMAP_FOLDER,
                readonly=True,
            )
            if status != "OK":
                raise RuntimeError(
                    f"Could not select Zoho IMAP folder {ZOHO_IMAP_FOLDER!r}."
                )

            logger.info("Zoho IMAP connected successfully using %s.", host)
            return mailbox

        except Exception as exc:
            last_error = exc
            logger.warning("Zoho IMAP connection/login failed on %s: %s", host, exc)
            if mailbox is not None:
                try:
                    mailbox.logout()
                except Exception:
                    pass

    raise RuntimeError(
        "Zoho IMAP connection/login failed. Verify ZOHO_IMAP_EMAIL, "
        "ZOHO_IMAP_PASSWORD (App Password), IMAP access, and the Zoho mailbox server. "
        f"Last error: {last_error}"
    )

def _message_text_and_attachments(msg):
    """Extract readable body text and file attachments from an EmailMessage."""
    plain_parts: list[str] = []
    html_parts: list[str] = []
    attachments: list[dict] = []

    if msg.is_multipart():
        parts = msg.walk()
    else:
        parts = [msg]

    for part in parts:
        if part.is_multipart():
            continue

        filename = part.get_filename()
        disposition = (part.get_content_disposition() or "").lower()
        content_type = (part.get_content_type() or "").lower()

        # Any named attachment is a real file attachment.
        if filename or disposition == "attachment":
            if not filename:
                filename = "attachment"
            try:
                payload = part.get_payload(decode=True) or b""
            except Exception:
                payload = b""
            if payload:
                attachments.append({
                    "filename": _decode_mime_header(filename),
                    "mime_type": content_type or "application/octet-stream",
                    "data": payload,
                    "size": len(payload),
                })
            continue

        # Ignore inline images/binaries for the dashboard attachment count.
        if content_type.startswith("image/") and disposition == "inline":
            continue

        try:
            value = part.get_content()
        except Exception:
            raw = part.get_payload(decode=True) or b""
            charset = part.get_content_charset() or "utf-8"
            try:
                value = raw.decode(charset, errors="replace")
            except Exception:
                value = raw.decode("utf-8", errors="replace")

        if not isinstance(value, str):
            continue

        if content_type == "text/plain":
            plain_parts.append(value)
        elif content_type == "text/html":
            html_parts.append(value)

    if plain_parts:
        body = "\n\n".join(x.strip() for x in plain_parts if x.strip())
    elif html_parts:
        body = _html_to_text("\n\n".join(html_parts))
    else:
        body = ""

    return body, attachments


def _zoho_fetch_uid_sync(uid: bytes | str) -> dict:
    mailbox = _zoho_open()
    try:
        uid_text = uid.decode() if isinstance(uid, bytes) else str(uid)
        status, data = mailbox.uid(
            "fetch",
            uid_text,
            "(BODY.PEEK[])"
        )
        if status != "OK":
            raise RuntimeError(
                f"Zoho IMAP fetch failed for UID {uid_text}: {data!r}"
            )

        raw_message = None
        for item in data or []:
            if isinstance(item, tuple) and len(item) >= 2:
                raw_message = item[1]
                break

        if not raw_message:
            raise RuntimeError(
                f"Zoho IMAP returned no message data for UID {uid_text}."
            )

        msg = BytesParser(policy=policy.default).parsebytes(raw_message)

        sender = parseaddr(msg.get("From", ""))[1].strip().lower()
        to_values = [
            parseaddr(x)[1].strip().lower()
            for x in msg.get_all("To", [])
            if parseaddr(x)[1]
        ]

        body, attachments = _message_text_and_attachments(msg)

        # UID is stable within the mailbox and avoids collisions with Graph IDs.
        message_id = (msg.get("Message-ID") or "").strip()
        stable_id = (
            f"zoho:{message_id}"
            if message_id
            else f"zoho-uid:{uid_text}"
        )

        return {
            "id": stable_id,
            "uid": uid_text,
            "thread_id": None,
            "internet_message_id": message_id or None,
            "in_reply_to": (msg.get("In-Reply-To") or "").strip().lower(),
            "references": (msg.get("References") or "").strip().lower(),
            "from": sender,
            "to": ", ".join(x for x in to_values if x),
            "subject": _decode_mime_header(msg.get("Subject", "")),
            "date": _iso_date(msg.get("Date", "")),
            "body": body,
            "body_type": "text/plain",
            "reply_text": body,
            "has_attachments": bool(attachments),
            "parent_folder_id": ZOHO_IMAP_FOLDER,
            "attachments": attachments,
        }
    finally:
        try:
            mailbox.close()
        except Exception:
            pass
        try:
            mailbox.logout()
        except Exception:
            pass


def _zoho_fetch_raw_message(mailbox: imaplib.IMAP4_SSL, uid: bytes | str) -> bytes:
    uid_text = uid.decode() if isinstance(uid, bytes) else str(uid)
    status, data = mailbox.uid("fetch", uid_text, "(BODY.PEEK[])")
    if status != "OK":
        raise RuntimeError(f"Zoho IMAP fetch failed for UID {uid_text}: {data!r}")

    for item in data or []:
        if isinstance(item, tuple) and len(item) >= 2 and item[1]:
            return item[1]

    raise RuntimeError(f"Zoho IMAP returned no message data for UID {uid_text}.")


def _zoho_message_from_raw(raw_message: bytes, uid_text: str) -> dict:
    msg = BytesParser(policy=policy.default).parsebytes(raw_message)

    sender = parseaddr(msg.get("From", ""))[1].strip().lower()
    to_values = [
        parseaddr(x)[1].strip().lower()
        for x in msg.get_all("To", [])
        if parseaddr(x)[1]
    ]

    body, attachments = _message_text_and_attachments(msg)

    message_id = (msg.get("Message-ID") or "").strip()
    stable_id = f"zoho:{message_id}" if message_id else f"zoho-uid:{uid_text}"

    return {
        "id": stable_id,
        "uid": uid_text,
        "thread_id": None,
        "internet_message_id": message_id or None,
        "in_reply_to": (msg.get("In-Reply-To") or "").strip().lower(),
        "references": (msg.get("References") or "").strip().lower(),
        "from": sender,
        "to": ", ".join(x for x in to_values if x),
        "subject": _decode_mime_header(msg.get("Subject", "")),
        "date": _iso_date(msg.get("Date", "")),
        "body": body,
        "body_type": "text/plain",
        "reply_text": body,
        "has_attachments": bool(attachments),
        "parent_folder_id": ZOHO_IMAP_FOLDER,
        "attachments": attachments,
    }


def _zoho_fetch_uid_sync(uid: bytes | str) -> dict:
    """Fetch one message (compatibility helper)."""
    mailbox = _zoho_open()
    try:
        uid_text = uid.decode() if isinstance(uid, bytes) else str(uid)
        return _zoho_message_from_raw(
            _zoho_fetch_raw_message(mailbox, uid_text),
            uid_text,
        )
    finally:
        try:
            mailbox.close()
        except Exception:
            pass
        try:
            mailbox.logout()
        except Exception:
            pass


def _zoho_find_incoming_sync(
    limit: int,
    allowed_senders: set[str] | None = None,
    after_uid: int | None = None,
) -> _ReplyScan:
    """Read recent/new Zoho messages using one IMAP connection."""
    mailbox = _zoho_open()
    try:
        if after_uid is not None and after_uid >= 0:
            status, data = mailbox.uid("search", None, "UID", f"{after_uid}:*")
        else:
            status, data = mailbox.uid("search", None, "ALL")

        if status != "OK":
            raise RuntimeError(f"Zoho IMAP search failed: {data!r}")

        raw_uids = (data[0] or b"").split()
        numeric_uids = [int(x) for x in raw_uids if str(x).isdigit()]
        latest_uid = max(numeric_uids) if numeric_uids else after_uid

        # First sync: cap initial work. Later syncs: inspect only new UIDs.
        if after_uid is None:
            raw_uids = raw_uids[-max(1, limit):]

        checkpoint = f"zoho:{latest_uid}" if latest_uid is not None else None
        results = _ReplyScan(history_id=checkpoint)

        allowed = {
            (x or "").strip().lower().replace("\\@", "@")
            for x in (allowed_senders or set())
            if x
        }

        for uid in reversed(raw_uids):
            uid_text = uid.decode(errors="ignore") if isinstance(uid, bytes) else str(uid)
            try:
                status, header_data = mailbox.uid(
                    "fetch",
                    uid_text,
                    "(BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE MESSAGE-ID IN-REPLY-TO REFERENCES)])",
                )
                if status != "OK":
                    continue

                raw_header = None
                for item in header_data or []:
                    if isinstance(item, tuple) and len(item) >= 2:
                        raw_header = item[1]
                        break
                if not raw_header:
                    continue

                header_msg = BytesParser(policy=policy.default).parsebytes(raw_header)
                sender = parseaddr(header_msg.get("From", ""))[1].strip().lower()

                if allowed and sender not in allowed:
                    continue

                raw_message = _zoho_fetch_raw_message(mailbox, uid_text)
                results.append(_zoho_message_from_raw(raw_message, uid_text))

                if len(results) >= limit:
                    break

            except Exception:
                logger.exception("Could not read Zoho message UID %s", uid_text)

        return results
    finally:
        try:
            mailbox.close()
        except Exception:
            pass
        try:
            mailbox.logout()
        except Exception:
            pass


async def find_incoming_replies(
    *,
    start_history_id: str | None = None,
    after_message_id: str | None = None,
    max_results: int = 500,
    allowed_senders: set[str] | None = None,
) -> _ReplyScan:
    """Find replies from the mailbox that actually receives qhtalbros.com mail.

    The current domain mail is landing in Zoho, so Zoho IMAP is the primary
    inbound source. Microsoft Graph remains the outbound sender. The Graph
    fallback is retained only for installations where Zoho IMAP variables are
    not configured.
    """
    del start_history_id
    del after_message_id

    limit = max(1, min(int(max_results or 500), 500))

    if _zoho_ready():
        after_uid = None
        if start_history_id:
            checkpoint = str(start_history_id).strip()
            if checkpoint.lower().startswith("zoho:"):
                checkpoint = checkpoint.split(":", 1)[1]
            if checkpoint.isdigit():
                after_uid = int(checkpoint)

        logger.info(
            "Checking Zoho IMAP inbox %s for incoming replies (after UID %s).",
            ZOHO_IMAP_EMAIL,
            after_uid,
        )
        result = await asyncio.to_thread(
            _zoho_find_incoming_sync,
            limit,
            allowed_senders,
            after_uid,
        )
        logger.info(
            "Zoho IMAP incoming scan found %d relevant message(s).",
            len(result),
        )
        return result

    # No Zoho credentials: preserve the Microsoft Graph path as a fallback.
    access_token = _get_microsoft_access_token()
    select = (
        "id,conversationId,internetMessageId,subject,from,toRecipients,"
        "receivedDateTime,body,hasAttachments,parentFolderId,internetMessageHeaders"
    )

    headers = _graph_headers(access_token)
    urls = [
        "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages",
        "https://graph.microsoft.com/v1.0/me/messages",
    ]

    seen_ids: set[str] = set()
    output = _ReplyScan()
    own_sender = _normalize_email_address(MICROSOFT_SENDER_EMAIL)

    async with httpx.AsyncClient(timeout=30.0) as client:
        for url_index, url in enumerate(urls):
            next_url = url
            params = {
                "$top": "100",
                "$orderby": "receivedDateTime desc",
                "$select": select,
            }
            pages = 0

            while next_url and len(output) < limit and pages < 10:
                response = await client.get(
                    next_url,
                    headers=headers,
                    params=params if next_url == url else None,
                )
                pages += 1

                if response.status_code != 200:
                    try:
                        detail = response.json()
                    except Exception:
                        detail = response.text
                    logger.warning(
                        "Microsoft Graph mail scan failed for %s (HTTP %s): %s",
                        next_url,
                        response.status_code,
                        detail,
                    )
                    if url_index == 0:
                        break
                    raise RuntimeError(
                        f"Microsoft Graph mailbox read failed (HTTP {response.status_code}): {detail}"
                    )

                data = response.json()
                messages = data.get("value", [])

                for message in messages:
                    message_id = message.get("id")
                    if not message_id or message_id in seen_ids:
                        continue
                    seen_ids.add(message_id)

                    sender = _graph_address(message.get("from") or {})
                    if own_sender and _normalize_email_address(sender) == own_sender:
                        continue

                    body = message.get("body") or {}
                    body_type = (body.get("contentType") or "").lower()
                    body_content = body.get("content") or ""
                    reply_text = (
                        _html_to_text(body_content)
                        if body_type == "html"
                        else body_content.strip()
                    )

                    recipients = [
                        _graph_address(x)
                        for x in (message.get("toRecipients") or [])
                    ]

                    headers_map = {}
                    for h in message.get("internetMessageHeaders") or []:
                        name = (h.get("name") or "").lower().strip()
                        if name:
                            headers_map[name] = h.get("value") or ""

                    output.append({
                        "id": message_id,
                        "thread_id": message.get("conversationId"),
                        "internet_message_id": message.get("internetMessageId"),
                        "in_reply_to": headers_map.get("in-reply-to", ""),
                        "references": headers_map.get("references", ""),
                        "from": sender,
                        "to": ", ".join(x for x in recipients if x),
                        "subject": message.get("subject") or "",
                        "date": message.get("receivedDateTime") or "",
                        "body": body_content,
                        "body_type": body_type,
                        "reply_text": reply_text,
                        "has_attachments": bool(message.get("hasAttachments")),
                        "parent_folder_id": message.get("parentFolderId"),
                    })

                next_url = data.get("@odata.nextLink")
                params = None

                if not messages or not next_url:
                    break

    output.sort(key=lambda item: item.get("date") or "", reverse=True)
    return output[:limit]


async def get_message_attachments(message_id: str) -> list[dict]:
    """Download attachments for a reply message from Zoho or Graph."""
    if message_id.startswith("zoho:") or message_id.startswith("zoho-uid:"):
        details = await get_incoming_message_details(message_id)
        return details.get("attachments", [])

    access_token = _get_microsoft_access_token()
    url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}/attachments"

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(
            url,
            headers=_graph_headers(access_token),
            params={"$top": "100"},
        )

    if response.status_code != 200:
        try:
            detail = response.json()
        except Exception:
            detail = response.text
        raise RuntimeError(
            f"Microsoft Graph attachment list failed (HTTP {response.status_code}): {detail}"
        )

    results = []
    for item in response.json().get("value", []):
        if item.get("@odata.type", "") != "#microsoft.graph.fileAttachment":
            continue

        content_bytes = item.get("contentBytes")
        attachment_id = item.get("id")
        filename = item.get("name") or "attachment"
        mime_type = item.get("contentType") or "application/octet-stream"

        if not content_bytes and attachment_id:
            async with httpx.AsyncClient(timeout=60.0) as client:
                one = await client.get(
                    f"{url}/{attachment_id}",
                    headers=_graph_headers(access_token),
                )
            if one.status_code != 200:
                continue
            item = one.json()
            content_bytes = item.get("contentBytes")

        if not content_bytes:
            continue

        try:
            file_data = base64.b64decode(content_bytes)
        except Exception:
            logger.exception("Could not decode Microsoft attachment %s", filename)
            continue

        results.append({
            "filename": filename,
            "mime_type": mime_type,
            "data": file_data,
            "size": len(file_data),
        })

    return results


async def get_incoming_message_details(message_id: str) -> dict:
    """Get one reply's body and attachments from Zoho or Graph."""
    if message_id.startswith("zoho:") or message_id.startswith("zoho-uid:"):
        uid_or_message_id = message_id
        return await asyncio.to_thread(
            _zoho_get_message_details_sync,
            uid_or_message_id,
        )

    access_token = _get_microsoft_access_token()
    url = f"https://graph.microsoft.com/v1.0/me/messages/{message_id}"
    params = {
        "$select": (
            "id,conversationId,internetMessageId,subject,from,toRecipients,"
            "receivedDateTime,body,hasAttachments"
        )
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.get(
            url,
            headers=_graph_headers(access_token),
            params=params,
        )

    if response.status_code != 200:
        try:
            detail = response.json()
        except Exception:
            detail = response.text
        raise RuntimeError(
            f"Microsoft Graph message read failed (HTTP {response.status_code}): {detail}"
        )

    message = response.json()
    body = message.get("body") or {}
    body_type = (body.get("contentType") or "").lower()
    body_content = body.get("content") or ""
    reply_text = (
        _html_to_text(body_content)
        if body_type == "html"
        else body_content.strip()
    )

    attachments = []
    if message.get("hasAttachments"):
        attachments = await get_message_attachments(message_id)

    sender = _graph_address(message.get("from") or {})
    recipients = [
        _graph_address(x)
        for x in (message.get("toRecipients") or [])
    ]

    return {
        "id": message.get("id") or message_id,
        "thread_id": message.get("conversationId"),
        "internet_message_id": message.get("internetMessageId"),
        "from": sender,
        "to": ", ".join(x for x in recipients if x),
        "subject": message.get("subject") or "",
        "date": message.get("receivedDateTime") or "",
        "body": body_content,
        "body_type": body_type,
        "reply_text": reply_text,
        "attachments": attachments,
    }


def _zoho_get_message_details_sync(message_id: str) -> dict:
    mailbox = _zoho_open()
    try:
        uid_text = None

        if message_id.startswith("zoho-uid:"):
            uid_text = message_id.split(":", 1)[1]
        elif message_id.startswith("zoho:"):
            # Resolve Message-ID back to its IMAP UID.
            wanted = message_id.split(":", 1)[1]
            status, data = mailbox.uid(
                "search",
                None,
                'HEADER', 'Message-ID', wanted.strip('<>'),
            )
            if status != "OK" or not data or not data[0]:
                raise RuntimeError(
                    f"Could not find Zoho message {wanted!r} in INBOX."
                )
            uid_text = data[0].split()[-1].decode()

        return _zoho_fetch_uid_sync(uid_text)
    finally:
        try:
            mailbox.close()
        except Exception:
            pass
        try:
            mailbox.logout()
        except Exception:
            pass

