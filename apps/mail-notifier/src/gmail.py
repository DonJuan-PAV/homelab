"""
Gmail mailbox: reads unread emails over IMAP with an app password.

Read-only: the inbox is opened in read-only mode and messages are fetched
with BODY.PEEK, so nothing is ever marked as read.

By default only the "Primary" tab is checked, so Promotions, Social and
Updates (where most ads land) never count.
"""

import email
import imaplib
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime

from models import Email

HOST = "imap.gmail.com"
PORT = 993

# Gmail search syntax (the same as the Gmail search bar)
DEFAULT_SEARCH = "in:inbox category:primary is:unread newer_than:2d"


def parse_headers(raw: bytes) -> tuple[str, str, str]:
    """
    Turn raw email headers into (subject, sender address, received date).
    Handles encoded subjects like =?UTF-8?B?...?= (accents, emojis).
    """
    msg = email.message_from_bytes(raw)
    subject = str(make_header(decode_header(msg.get("Subject", "")))).strip()
    sender = parseaddr(msg.get("From", ""))[1] or "unknown"
    try:
        received = parsedate_to_datetime(msg.get("Date", "")).isoformat()
    except (TypeError, ValueError):
        received = ""
    return subject, sender, received


class GmailMailbox:
    def __init__(self, name: str, address: str, app_password: str,
                 search: str = DEFAULT_SEARCH):
        self.name = name                  # label on the dashboard, e.g. "gmail"
        self.address = address            # your Gmail address
        self.app_password = app_password  # 16-character app password, not your real password
        self.search = search

    def fetch_unread(self, limit: int = 25) -> list[Email]:
        emails = []
        with imaplib.IMAP4_SSL(HOST, PORT, timeout=30) as imap:
            imap.login(self.address, self.app_password)
            imap.select("INBOX", readonly=True)  # read-only: never changes anything

            # UIDVALIDITY + UID together identify an email forever
            validity = (imap.response("UIDVALIDITY")[1] or [b"0"])[0]
            validity = validity.decode() if isinstance(validity, bytes) else str(validity)

            # X-GM-RAW lets us use Gmail's own search syntax over IMAP
            status, data = imap.uid("SEARCH", "X-GM-RAW", f'"{self.search}"')
            if status != "OK":
                raise RuntimeError(f"Gmail search failed: {data}")
            uids = data[0].split()[-limit:]  # newest last, keep the most recent

            for uid in uids:
                status, parts = imap.uid(
                    "FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])")
                if status != "OK" or not parts or not isinstance(parts[0], tuple):
                    continue
                subject, sender, received = parse_headers(parts[0][1])
                emails.append(Email(
                    id=f"{validity}-{uid.decode()}",
                    account=self.name,
                    subject=subject,
                    sender=sender,
                    received=received,
                ))
        return emails
