"""
mail-notifier - counts important emails from Outlook and Gmail
and shows the numbers on the Homepage dashboard.

Every POLL_SECONDS seconds, for each mailbox:
  1. Read the unread emails (read-only: nothing is marked as read).
  2. Ignore the ones already counted.
  3. Skip noise: replies, forwards, auto-replies, no-reply senders, ads, spam.
  4. Count the important ones.
The counts are served at http://SERVER:PORT/stats for Homepage.

Run it:
    python src/main.py          # runs forever (Ctrl+C to stop)
    python src/main.py --once   # one check, then exit (handy for testing)
"""

import argparse
import logging
import os
import signal
import sys
import threading
from datetime import datetime

from config import load_settings, validate
from filters import get_skip_reason
from gmail import DEFAULT_SEARCH, GmailMailbox
from outlook import OutlookMailbox
from stats_server import start_stats_server
from store import Store

log = logging.getLogger("mail-notifier")


def check_mailbox(mailbox, store: Store) -> dict:
    """Check one mailbox and count new important emails."""
    counts = {"important": 0, "skipped": 0}
    for email in mailbox.fetch_unread():
        if store.is_seen(email):
            continue  # already counted on an earlier check
        reason = get_skip_reason(email.subject, email.sender)
        store.mark_seen(email, important=reason is None, skip_reason=reason)
        if reason:
            counts["skipped"] += 1
            log.info("Skipped [%s] \"%s\" -> %s", email.account, email.subject, reason)
        else:
            counts["important"] += 1
            log.info("IMPORTANT [%s] \"%s\" from %s", email.account, email.subject, email.sender)
    return counts


def check_all(mailboxes: list, store: Store) -> None:
    """
    Check every mailbox. One mailbox failing (Gmail down, expired login...)
    never stops the others from being checked.
    """
    for mailbox in mailboxes:
        try:
            counts = check_mailbox(mailbox, store)
            if any(counts.values()):
                log.info("[%s] new: %s", mailbox.name, counts)
        except Exception as exc:
            log.error("[%s] check failed, will retry: %s", mailbox.name, exc)
    store.set_meta("last_check", datetime.now().astimezone().isoformat(timespec="seconds"))


def build_mailboxes(settings) -> list:
    mailboxes = []
    if settings.outlook_client_id:
        mailboxes.append(OutlookMailbox(
            name="outlook",
            client_id=settings.outlook_client_id,
            cache_path=os.path.join(settings.data_dir, "outlook_token.json"),
            focused_only=settings.outlook_focused_only,
        ))
    if settings.gmail_address:
        mailboxes.append(GmailMailbox(
            name="gmail",
            address=settings.gmail_address,
            app_password=settings.gmail_app_password,
            search=settings.gmail_search or DEFAULT_SEARCH,
        ))
    return mailboxes


def main() -> None:
    parser = argparse.ArgumentParser(description="Count important emails for the dashboard.")
    parser.add_argument("--once", action="store_true", help="check once and exit")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    settings = load_settings()
    problems = validate(settings)
    if problems:
        for problem in problems:
            log.error(problem)
        sys.exit("Fix the settings in your .env file, then try again.")

    os.makedirs(settings.data_dir, exist_ok=True)
    store = Store(os.path.join(settings.data_dir, "notifier.db"))
    mailboxes = build_mailboxes(settings)
    names = [m.name for m in mailboxes]

    if args.once:
        check_all(mailboxes, store)
        log.info("Stats: %s", store.stats(names))
        return

    if settings.stats_port:
        start_stats_server(lambda: store.stats(names), settings.stats_host, settings.stats_port)
        log.info("Dashboard numbers at http://<server-ip>:%s/stats", settings.stats_port)

    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())

    log.info("Watching %s every %s s", ", ".join(names), settings.poll_seconds)
    while not stop.is_set():
        check_all(mailboxes, store)
        stop.wait(settings.poll_seconds)
    log.info("Stopped.")


if __name__ == "__main__":
    main()
