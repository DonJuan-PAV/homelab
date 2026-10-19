"""Gmail reader against a FAKE IMAP server (no Gmail account needed)."""

from unittest.mock import MagicMock, patch

from gmail import GmailMailbox

HEADERS = {
    b"101": b"Subject: Dinner Saturday?\r\nFrom: Marie <marie@example.com>\r\n"
            b"Date: Sat, 18 Oct 2026 14:00:00 -0400\r\n\r\n",
    b"102": b"Subject: Flight confirmed\r\nFrom: trips@airline.com\r\n\r\n",
}


def fake_imap():
    imap = MagicMock()
    imap.__enter__.return_value = imap
    imap.response.return_value = ("UIDVALIDITY", [b"777"])

    def uid(command, *args):
        if command == "SEARCH":
            return "OK", [b"101 102"]
        if command == "FETCH":
            return "OK", [(b"header", HEADERS[args[0]]), b")"]
    imap.uid.side_effect = uid
    return imap


def test_reads_unread_without_changing_anything():
    imap = fake_imap()
    with patch("gmail.imaplib.IMAP4_SSL", return_value=imap):
        emails = GmailMailbox("gmail", "me@gmail.com", "apppassword").fetch_unread()

    assert [e.subject for e in emails] == ["Dinner Saturday?", "Flight confirmed"]
    assert emails[0].sender == "marie@example.com"
    assert emails[0].id == "777-101" and emails[0].account == "gmail"

    imap.select.assert_called_once_with("INBOX", readonly=True)  # never marks as read
    fetch_args = [c.args for c in imap.uid.call_args_list if c.args[0] == "FETCH"]
    assert all("BODY.PEEK" in args[2] for args in fetch_args)


def test_uses_primary_tab_search_by_default():
    imap = fake_imap()
    with patch("gmail.imaplib.IMAP4_SSL", return_value=imap):
        GmailMailbox("gmail", "me@gmail.com", "apppassword").fetch_unread()
    search = [c.args for c in imap.uid.call_args_list if c.args[0] == "SEARCH"][0]
    assert search[1] == "X-GM-RAW" and "category:primary" in search[2]
