"""Gmail access. One small interface, two backends: the real Gmail API and an in-memory demo inbox."""

import base64
import hashlib
import html
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from cryptography.fernet import Fernet
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.credentials import Credentials

from . import db
from .config import settings

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
API = "https://gmail.googleapis.com/gmail/v1/users/me"
HEADERS = ["From", "To", "Subject", "List-Unsubscribe"]
_pool = ThreadPoolExecutor(16)


def _fernet():
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(settings.secret_key.encode() + b"|tokens").digest()))


def encrypt(text):
    return _fernet().encrypt(text.encode()).decode()


def decrypt(text):
    return _fernet().decrypt(text.encode()).decode()


class Gmail:
    """Real Gmail API backend."""

    def __init__(self):
        self._creds, self._labels, self._lock = {}, {}, threading.Lock()

    def _credentials(self, email):
        with self._lock:
            if email not in self._creds:
                box = db.rows("SELECT * FROM mailboxes WHERE email=?", email)[0]
                self._creds[email] = Credentials(
                    None, refresh_token=decrypt(box["refresh_token"]), token_uri="https://oauth2.googleapis.com/token",
                    client_id=settings.google_client_id, client_secret=settings.google_client_secret, scopes=SCOPES)
            return self._creds[email]

    def call(self, email, method, path, **kw):
        for attempt in range(4):
            r = AuthorizedSession(self._credentials(email)).request(method, API + path, timeout=60, **kw)
            if r.status_code in (429, 500, 502, 503) and attempt < 3:
                time.sleep(2 ** attempt)
                continue
            if r.status_code >= 400:
                raise RuntimeError(f"Gmail {r.status_code} for {email}: {r.text[:200]}")
            return r.json() if r.content else {}

    def profile(self, email):
        return self.call(email, "GET", "/profile")

    def candidates(self, email, min_age_hours, limit):
        """Unlabeled inbox mail, oldest-first cut off at `limit`, older than min_age_hours."""
        ids, token = [], None
        while len(ids) < limit:
            params = {"q": "in:inbox has:nouserlabels", "maxResults": min(500, limit - len(ids))}
            if token:
                params["pageToken"] = token
            page = self.call(email, "GET", "/messages", params=params)
            ids += [m["id"] for m in page.get("messages", [])]
            token = page.get("nextPageToken")
            if not token:
                break
        cutoff = (time.time() - min_age_hours * 3600) * 1000
        rows = list(_pool.map(lambda i: self._meta(email, i), ids))
        return [r for r in rows if r["ts"] <= cutoff]

    def _meta(self, email, message_id):
        m = self.call(email, "GET", f"/messages/{message_id}", params={"format": "metadata", "metadataHeaders": HEADERS})
        h = {x["name"].lower(): x["value"] for x in m["payload"].get("headers", [])}
        return {"id": m["id"], "thread": m["threadId"], "ts": int(m["internalDate"]), "from": h.get("from", ""),
                "to": h.get("to", ""), "subject": h.get("subject", ""), "bulk": "list-unsubscribe" in h,
                "snippet": html.unescape(m.get("snippet", ""))[:300], "unread": "UNREAD" in m.get("labelIds", [])}

    def label_id(self, email, path):
        """Return the Gmail label id for `path`, creating it (and its parents) on first use."""
        with self._lock:
            known = self._labels.get(email)
        if known is None:
            known = {l["name"].lower(): l["id"] for l in self.call(email, "GET", "/labels").get("labels", [])}
            with self._lock:
                self._labels[email] = known
        parts = path.split("/")
        for depth in range(1, len(parts) + 1):
            name = "/".join(parts[:depth])
            if name.lower() not in known:
                made = self.call(email, "POST", "/labels", json={
                    "name": name, "labelListVisibility": "labelShow", "messageListVisibility": "show"})
                known[name.lower()] = made["id"]
        return known[path.lower()]

    def modify(self, email, message_ids, add, remove):
        for i in range(0, len(message_ids), 1000):
            self.call(email, "POST", "/messages/batchModify",
                      json={"ids": message_ids[i:i + 1000], "addLabelIds": add, "removeLabelIds": remove})

    def link(self, email, thread_id):
        return f"https://mail.google.com/mail/u/{email}/#all/{thread_id}"


class DemoGmail(Gmail):
    """In-memory inbox used by DEMO_MODE: try the whole app without Google or Claude credentials."""

    def __init__(self):
        super().__init__()
        from .demo import demo_inboxes
        self.boxes = demo_inboxes()

    def profile(self, email):
        return {"emailAddress": email, "messagesTotal": len(self.boxes.get(email, []))}

    def candidates(self, email, min_age_hours, limit):
        cutoff = (time.time() - min_age_hours * 3600) * 1000
        return [dict(m) for m in self.boxes.get(email, []) if not m["user_labels"] and m["inbox"] and m["ts"] <= cutoff][:limit]

    def label_id(self, email, path):
        return path

    def modify(self, email, message_ids, add, remove):
        for m in self.boxes.get(email, []):
            if m["id"] in message_ids:
                m["user_labels"] += [a for a in add if a not in ("STARRED", "IMPORTANT")]
                if "INBOX" in remove:
                    m["inbox"] = False


_backend = None


def backend():
    global _backend
    if _backend is None:
        _backend = DemoGmail() if settings.demo_mode else Gmail()
    return _backend
