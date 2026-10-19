"""
Filter rules: decide whether an email is important (counted on the
dashboard) or noise (skipped). Same rules as mail2jira, plus ad senders.

Edit the lists below to change what gets skipped. Everything is
case-insensitive. English and French versions are included because
clients write in both.
"""

import re

# Subjects starting with these prefixes are replies or forwards of an existing
# conversation, so they should not open a brand-new ticket.
# RE = reply, FW/FWD = forward, TR = "transféré" (French forward)
SKIP_SUBJECT_PREFIXES = ["re", "fw", "fwd", "tr"]

# Subjects containing any of these phrases are automatic messages
# (out-of-office, delivery failures, read receipts...).
SKIP_SUBJECT_PHRASES = [
    "automatic reply", "auto reply", "autoreply", "out of office",
    "réponse automatique", "absent du bureau", "absence du bureau",
    "undeliverable", "delivery status notification", "mail delivery failed",
    "non remis", "read:", "lu :",
]

# Senders whose address contains any of these are robots, not real people.
SKIP_SENDER_PATTERNS = [
    "noreply", "no-reply", "no_reply", "donotreply", "do-not-reply",
    "mailer-daemon", "postmaster", "notifications@", "newsletter",
    # typical advertising senders
    "marketing", "promo", "deals@", "offers@", "news@", "mailer@", "bounce",
]

# Typical spam words found in subjects.
SPAM_KEYWORDS = [
    "you have won", "you've won", "congratulations", "lottery", "free gift",
    "claim your prize", "urgent action required", "verify your account",
    "bitcoin", "crypto", "unsubscribe", "limited time offer",
    "vous avez gagné", "félicitations", "offre limitée",
]

# One pattern built from the prefix list: ^\s*(re|fw|fwd|tr)\s*:
# Meaning: start of the subject, optional spaces, one of the prefixes,
# optional spaces, then a colon. "Re :" (French spacing) also matches,
# but "Treasury report" does not, because there is no colon after "tr".
PREFIX_PATTERN = re.compile(
    r"^\s*(" + "|".join(SKIP_SUBJECT_PREFIXES) + r")\s*:", re.IGNORECASE
)


def get_skip_reason(subject: str, sender: str) -> str | None:
    """
    Check an email against the filter rules.
    Returns a short reason if the email should be SKIPPED,
    or None if it is important and should become a ticket.
    """
    subject = subject or ""
    sender = sender or ""
    subject_lower = subject.lower()
    sender_lower = sender.lower()

    # Rule 1: replies and forwards (RE:, FW:, FWD:, TR:)
    match = PREFIX_PATTERN.match(subject)
    if match:
        return f"reply/forward ({match.group(1).upper()}:)"

    # Rule 2: robot senders (no-reply, mailer-daemon...)
    for pattern in SKIP_SENDER_PATTERNS:
        if pattern in sender_lower:
            return f"automated sender ({pattern})"

    # Rule 3: automatic messages (out of office, delivery failure...)
    for phrase in SKIP_SUBJECT_PHRASES:
        if phrase in subject_lower:
            return f"automatic message ({phrase})"

    # Rule 4: spam keywords
    for keyword in SPAM_KEYWORDS:
        if keyword in subject_lower:
            return f"possible spam ({keyword})"

    # Rule 5: empty subject, nothing to build a ticket title from
    if not subject.strip():
        return "empty subject"

    return None  # passed every rule: this one is important
