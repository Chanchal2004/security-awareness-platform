



1
2
3
4
5
6
7
8
9
10
11
12
13
14
15
16
17
18
19
20
21
22
23
24
25
26
27
28
29
30
31
32
33
34
35
36
37
38
39
40
41
42
43
44
45
46
47
48
49
50
51
52
53
54
55
56
57
58
59
60
61
62
63
64
65
66
67
68
69
70
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
                    "Link text must not reference a "
            pass
