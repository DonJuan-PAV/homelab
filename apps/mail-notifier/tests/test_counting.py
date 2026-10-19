"""Counting, duplicates and mailbox failures, with fake mailboxes."""

import json
import urllib.request

from conftest import make_email
from main import check_all
from stats_server import start_stats_server


class FakeMailbox:
    def __init__(self, name, emails=None, broken=False):
        self.name = name
        self.emails = emails or []
        self.broken = broken

    def fetch_unread(self):
        if self.broken:
            raise ConnectionError("cannot reach the mail server")
        return list(self.emails)


def test_counts_per_account_and_skips_noise(store):
    outlook = FakeMailbox("outlook", [
        make_email(id="1", account="outlook"),
        make_email(id="2", account="outlook", subject="RE: Dinner Saturday?"),
    ])
    gmail = FakeMailbox("gmail", [
        make_email(id="1", account="gmail", subject="Your flight is confirmed"),
        make_email(id="2", account="gmail", subject="50% off!", sender="promo@shop.com"),
    ])
    check_all([outlook, gmail], store)

    stats = store.stats(["outlook", "gmail"])
    assert stats["outlook_today"] == 1
    assert stats["gmail_today"] == 1
    assert stats["today"] == 2 and stats["total"] == 2


def test_each_email_counted_once(store):
    mailbox = FakeMailbox("outlook", [make_email(id="1")])
    for _ in range(5):
        check_all([mailbox], store)
    assert store.stats(["outlook"])["today"] == 1


def test_one_broken_mailbox_does_not_stop_the_other(store):
    broken = FakeMailbox("outlook", broken=True)
    gmail = FakeMailbox("gmail", [make_email(id="1", account="gmail")])
    check_all([broken, gmail], store)
    assert store.stats(["outlook", "gmail"])["gmail_today"] == 1


def test_accounts_with_no_mail_show_zero(store):
    stats = store.stats(["outlook", "gmail"])
    assert stats["outlook_today"] == 0 and stats["gmail_today"] == 0


def test_stats_never_expose_private_details(store):
    check_all([FakeMailbox("outlook", [make_email(subject="Secret plans",
                                                  sender="boss@example.com")])], store)
    text = json.dumps(store.stats(["outlook"]))
    assert "Secret plans" not in text and "boss@example.com" not in text


def test_stats_endpoint_for_homepage(store):
    check_all([FakeMailbox("gmail", [make_email(account="gmail")])], store)
    server = start_stats_server(lambda: store.stats(["outlook", "gmail"]), "127.0.0.1", 0)
    try:
        port = server.server_address[1]
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/stats") as response:
            data = json.load(response)
        assert data["gmail_today"] == 1 and data["outlook_today"] == 0
        assert data["last_check"]
    finally:
        server.shutdown()
