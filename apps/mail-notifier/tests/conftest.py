import pytest

from models import Email
from store import Store


def make_email(id="1", account="outlook", subject="Dinner Saturday?", sender="friend@example.com"):
    return Email(id=id, account=account, subject=subject, sender=sender,
                 received="2026-10-18T14:00:00Z")


@pytest.fixture
def store(tmp_path):
    return Store(str(tmp_path / "test.db"))
