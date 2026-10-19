"""The shape of an email inside the notifier, whatever mailbox it came from."""

from dataclasses import dataclass


@dataclass
class Email:
    id: str         # unique ID from the mail provider
    account: str    # which mailbox: "outlook", "gmail"...
    subject: str
    sender: str     # sender's email address
    received: str   # date and time received (ISO format)

    @property
    def key(self) -> str:
        """Unique even when several mailboxes are scanned."""
        return f"{self.account}:{self.id}"
