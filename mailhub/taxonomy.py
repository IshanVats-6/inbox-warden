"""The label taxonomy: a few fixed core labels plus labels the agent creates for each company.

Nothing is created in Gmail up front. A label is written to Gmail the first time an email is filed under it.
Dispositions decide what happens to mail with that label:
  inbox           stays in the inbox
  archive         leaves the inbox and is marked read
  archive_unread  leaves the inbox, stays unread (for labels you check on their own, like notifications)
"""

import difflib
import re

from . import db

DISPOSITIONS = ("inbox", "archive", "archive_unread")

CORE = [
    ("Finance", "Invoices, receipts, bills, payment confirmations or failures, refunds, payouts, renewals.", "inbox"),
    ("Notifications", "Automated alerts, digests, reports and activity from software tools.", "archive_unread"),
    ("Newsletters", "Editorial newsletters, podcasts and content digests.", "archive"),
    ("Promotions", "Marketing, product announcements, webinars, events and cold sales pitches.", "archive"),
]

MAX_DEPTH = 2
MAX_SEGMENT = 40


def seed():
    for path, description, disposition in CORE:
        db.execute("INSERT OR IGNORE INTO labels(path, description, disposition, origin, created_at) "
                   "VALUES(?, ?, ?, 'core', ?)", path, description, disposition, db.now())


def all_labels():
    return db.rows("SELECT * FROM labels ORDER BY path")


def clean_path(path):
    """Normalise a proposed label path: max two levels, tidy segments, no Gmail-reserved names."""
    parts = []
    for raw in str(path).replace("\\", "/").split("/")[:MAX_DEPTH]:
        seg = re.sub(r"[^\w &.\-+']", "", raw, flags=re.UNICODE)
        seg = re.sub(r"\s+", " ", seg).strip(" .-")[:MAX_SEGMENT]
        if seg:
            parts.append(seg[0].upper() + seg[1:])
    path = "/".join(parts)
    if not path or path.upper() in {"INBOX", "SPAM", "TRASH", "SENT", "DRAFT", "STARRED", "IMPORTANT", "UNREAD"}:
        return ""
    return path


def match_existing(path, existing):
    """Reuse an existing label when the proposal is the same label spelled slightly differently."""
    by_key = {p.lower(): p for p in existing}
    if path.lower() in by_key:
        return by_key[path.lower()]
    close = difflib.get_close_matches(path.lower(), list(by_key), n=1, cutoff=0.9)
    return by_key[close[0]] if close else None


def add(path, description, disposition, origin="agent"):
    disposition = disposition if disposition in DISPOSITIONS else "archive"
    parent = path.split("/")[0]
    if "/" in path and not db.rows("SELECT 1 FROM labels WHERE path=?", parent):
        # a new parent group inherits the child's disposition
        db.execute("INSERT OR IGNORE INTO labels(path, description, disposition, origin, created_at) "
                   "VALUES(?, '', ?, ?, ?)", parent, disposition, origin, db.now())
    db.execute("INSERT OR IGNORE INTO labels(path, description, disposition, origin, created_at) VALUES(?, ?, ?, ?, ?)",
               path, description[:200], disposition, origin, db.now())


def disposition_of(path):
    row = db.rows("SELECT disposition FROM labels WHERE path=?", path)
    if row:
        return row[0]["disposition"]
    parent = db.rows("SELECT disposition FROM labels WHERE path=?", path.split("/")[0])
    return parent[0]["disposition"] if parent else "archive"


def count(path, n):
    db.execute("UPDATE labels SET emails = emails + ? WHERE path=?", n, path)
