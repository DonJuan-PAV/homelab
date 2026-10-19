import pytest

from config import Settings, validate
from filters import get_skip_reason
from gmail import parse_headers


def test_parse_plain_headers():
    raw = (b"Subject: Dinner Saturday?\r\n"
           b"From: Marie Tremblay <marie@example.com>\r\n"
           b"Date: Sat, 18 Oct 2026 14:00:00 -0400\r\n\r\n")
    subject, sender, received = parse_headers(raw)
    assert subject == "Dinner Saturday?"
    assert sender == "marie@example.com"
    assert received.startswith("2026-10-18T14:00:00")


def test_parse_encoded_french_subject():
    # "Réunion" encoded the way email programs send accents
    raw = b"Subject: =?UTF-8?B?UsOpdW5pb24gZGVtYWlu?=\r\nFrom: a@example.com\r\n\r\n"
    subject, _, received = parse_headers(raw)
    assert subject == "Réunion demain"
    assert received == ""  # missing date doesn't crash


@pytest.mark.parametrize("sender", ["promo@shop.com", "deals@store.ca", "news@brand.com",
                                    "marketing@company.com", "noreply@bank.com"])
def test_ad_senders_are_skipped(sender):
    assert get_skip_reason("Big sale this weekend", sender) is not None


def _settings(**changes):
    base = dict(outlook_client_id="abc", outlook_focused_only=False, gmail_address="",
                gmail_app_password="", gmail_search="", poll_seconds=60, data_dir="data",
                stats_host="0.0.0.0", stats_port=8080)
    base.update(changes)
    return Settings(**base)


def test_outlook_only_is_valid():
    assert validate(_settings()) == []


def test_needs_at_least_one_mailbox():
    assert validate(_settings(outlook_client_id=""))


def test_gmail_needs_app_password():
    problems = validate(_settings(gmail_address="me@gmail.com"))
    assert any("GMAIL_APP_PASSWORD" in p for p in problems)
