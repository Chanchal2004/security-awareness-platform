import os
import re
import ipaddress
import logging
import json
import base64

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
        accounts = app.get_accounts()

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
    final_reply_to = reply_to or EMAIL_REPLY_TO
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
    return {"id": message_id, "thread_id": conversation_id}


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
    """List-compatible scan result that also supports the newer dict contract."""

    def get(self, key, default=None):
        if key == "messages":
            return list(self)
        if key == "history_id":
            return None
        return default


async def find_incoming_replies(
    *,
    start_history_id: str | None = None,
    after_message_id: str | None = None,
    max_results: int = 50,
) -> _ReplyScan:
    """Find incoming mail that can be a reply to a sent simulation.

    Microsoft Graph does not use Gmail history IDs.  We therefore scan both
    Inbox and the mailbox message collection.  Messages sent by our own
    Microsoft sender are explicitly ignored so the sync never treats our
    outgoing Graph emails as incoming replies.
    """
    del start_history_id
    del after_message_id

    access_token = _get_microsoft_access_token()
    top = max(1, min(int(max_results or 50), 100))
    select = (
        "id,conversationId,internetMessageId,subject,from,toRecipients,"
        "receivedDateTime,body,hasAttachments,parentFolderId"
    )

    headers = _graph_headers(access_token)
    # Inbox first: this is where an actual Gmail/recipient reply should land.
    # Mailbox-wide scan is kept as a fallback for messages Graph exposes outside
    # the Inbox.  We collect from both instead of stopping after the first
    # non-empty result, because the newest mailbox messages can be our own sent
    # messages and otherwise hide an older incoming reply.
    urls = [
        "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages",
        "https://graph.microsoft.com/v1.0/me/messages",
    ]

    seen_ids: set[str] = set()
    output = _ReplyScan()
    own_sender = _normalize_email_address(MICROSOFT_SENDER_EMAIL)

    async with httpx.AsyncClient(timeout=30.0) as client:
        for url_index, url in enumerate(urls):
            params = {
                "$top": str(top),
                "$orderby": "receivedDateTime desc",
                "$select": select,
            }

            response = await client.get(url, headers=headers, params=params)

            if response.status_code != 200:
                try:
                    detail = response.json()
                except Exception:
                    detail = response.text
                logger.warning(
                    "Microsoft Graph mail scan failed for %s (HTTP %s): %s",
                    url,
                    response.status_code,
                    detail,
                )
                if url_index == 0:
                    # Continue with mailbox-wide scan if Inbox access fails.
                    continue
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

                # IMPORTANT: /me/messages also contains our own Sent Items.
                # Never expose those to reply matching as incoming replies.
                if own_sender and _normalize_email_address(sender) == own_sender:
                    logger.debug("Skipping own outgoing Graph message %s", message_id)
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

                output.append({
                    "id": message_id,
                    "thread_id": message.get("conversationId"),
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

    output.sort(key=lambda item: item.get("date") or "", reverse=True)
    return output[:top]


async def get_message_attachments(message_id: str) -> list[dict]:
    """Download file attachments from a Microsoft Graph message."""
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
        odata_type = item.get("@odata.type", "")
        if odata_type != "#microsoft.graph.fileAttachment":
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
                logger.warning(
                    "Could not download Microsoft attachment %s from message %s: HTTP %s",
                    filename, message_id, one.status_code,
                )
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
    """Get one Microsoft Graph message, body text and its file attachments."""
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
        "message_id": message_id,
        "thread_id": message.get("conversationId"),
        "from": sender,
        "to": ", ".join(x for x in recipients if x),
        "subject": message.get("subject") or "",
        "date": message.get("receivedDateTime") or "",
        "reply_text": reply_text,
        "attachments": attachments,
    }
