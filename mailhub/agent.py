"""One cleanup run: fetch unlabeled inbox mail, ask Claude, enforce the guardrails, apply, record."""

import collections
import json
import threading
import traceback

import requests

from . import db, taxonomy
from .classifier import classifier
from .config import settings
from .gmail import backend

_running = threading.Lock()

# action -> (labels to add besides the folder label, labels to remove)
ACTIONS = {
    "keep": ([], []),
    "attention": (["STARRED", "IMPORTANT"], []),
    "archive": ([], ["INBOX", "UNREAD"]),
    "archive_unread": ([], ["INBOX"]),
    "label": ([], []),
}


def default_company():
    return {"name": "", "description": ""}


def is_dry_run():
    return db.get("dry_run", True)


def decide_action(disposition, attention, mode):
    if mode == "label_only":
        return "label"
    if attention:
        return "attention"
    return {"inbox": "keep", "archive": "archive", "archive_unread": "archive_unread"}[disposition]


def run(trigger="manual", dry_run=None):
    if not _running.acquire(blocking=False):
        return None
    dry_run = is_dry_run() if dry_run is None else dry_run
    run_id = db.execute("INSERT INTO runs(started_at, trigger, dry_run) VALUES(?, ?, ?)", db.now(), trigger, int(dry_run))
    stats = collections.Counter()
    try:
        _run(run_id, dry_run, stats)
        db.execute("UPDATE runs SET finished_at=?, status='done', stats=? WHERE id=?", db.now(), json.dumps(stats), run_id)
    except Exception as ex:
        traceback.print_exc()
        db.execute("UPDATE runs SET finished_at=?, status='failed', stats=?, error=? WHERE id=?",
                   db.now(), json.dumps(stats), str(ex)[:500], run_id)
    finally:
        _running.release()
    notify(run_id)
    return run_id


def _run(run_id, dry_run, stats):
    gmail, brain = backend(), classifier()
    company = db.get("company", default_company())
    boxes = db.rows("SELECT * FROM mailboxes WHERE mode != 'paused' ORDER BY email")
    emails, budget = [], settings.max_emails_per_run
    for box in boxes:
        if budget <= 0:
            break
        found = gmail.candidates(box["email"], box["min_age_hours"], budget)
        for e in found:
            e["mailbox"], e["mode"] = box["email"], box["mode"]
        emails += found
        budget -= len(found)
    stats["fetched"] = len(emails)

    pending = {}  # labels proposed this run (kept in memory during dry runs)
    new_label_budget = settings.max_new_labels_per_run
    plan = collections.defaultdict(list)
    for start in range(0, len(emails), settings.batch_size):
        batch = emails[start:start + settings.batch_size]
        labels = taxonomy.all_labels() + list(pending.values())
        try:
            decisions, usage = brain.classify(batch, labels, company)
        except Exception as ex:  # one bad batch (API error, refusal) leaves those emails untouched for next run
            stats["batch_errors"] += 1
            stats["skipped"] += len(batch)
            stats["last_error"] = str(ex)[:200]
            continue
        if usage:
            stats["input_tokens"] += usage.input_tokens
            stats["output_tokens"] += usage.output_tokens
            stats["cache_read_tokens"] += usage.cache_read_input_tokens or 0
        by_id = {e["id"]: e for e in batch}
        for d in decisions:
            e = by_id.get(d.id)
            if not e:
                continue
            path = taxonomy.clean_path(d.label)
            known = [l["path"] for l in labels] + list(pending)
            existing = taxonomy.match_existing(path, known) if path else None
            new = False
            if not existing:
                if not path or new_label_budget <= 0:
                    stats["skipped"] += 1
                    continue
                new, new_label_budget = True, new_label_budget - 1
                pending[path] = {"path": path, "description": d.new_label_description,
                                 "disposition": d.new_label_disposition, "origin": "agent"}
                if not dry_run:
                    taxonomy.add(path, d.new_label_description, d.new_label_disposition)
                stats["labels_created"] += 1
                existing = path
            disposition = pending[existing]["disposition"] if existing in pending else taxonomy.disposition_of(existing)
            action = decide_action(disposition, d.needs_attention, e["mode"])
            plan[(e["mailbox"], existing, action)].append(e)
            stats[action] += 1
            stats["sorted"] += 1
            db.execute("INSERT INTO decisions VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", run_id, e["mailbox"], e["id"],
                       e["thread"], e["from"][:200], e["subject"][:300], existing, action, int(d.needs_attention),
                       int(new), d.reason[:200], db.now())

    if dry_run:
        return
    for (mailbox, path, action), items in plan.items():
        add, remove = ACTIONS[action]
        gmail.modify(mailbox, [e["id"] for e in items], [gmail.label_id(mailbox, path)] + add, remove)
        taxonomy.count(path, len(items))


def notify(run_id):
    if not settings.slack_webhook_url:
        return
    run = db.rows("SELECT * FROM runs WHERE id=?", run_id)[0]
    stats = json.loads(run["stats"])
    urgent = db.rows("SELECT * FROM decisions WHERE run_id=? AND action='attention'", run_id)
    lines = [f"*Mailhub* {'(preview) ' if run['dry_run'] else ''}sorted {stats.get('sorted', 0)} emails, "
             f"archived {stats.get('archive', 0) + stats.get('archive_unread', 0)}, "
             f"created {stats.get('labels_created', 0)} labels."]
    if run["status"] == "failed":
        lines.append(f"Run failed: {run['error']}")
    for d in urgent[:10]:
        lines.append(f"• *{d['subject'] or '(no subject)'}* from {d['sender']} ({d['mailbox']})")
    try:
        requests.post(settings.slack_webhook_url, json={"text": "\n".join(lines)}, timeout=10)
    except requests.RequestException:
        pass
