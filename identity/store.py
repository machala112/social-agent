"""Identity store: multiple persistent social identities per installation.

Layout under ``<home>/identity/``::

    accounts/          per social account: handle, platform, persona file,
                       owner name            (<label>.json)
    permissions/       per-identity grants (<id>.json)
    identities.db      SQLite registry tying it all together

An identity is a persona + account mapping + permission set. Execution
happens in the external agent's browser (see hands/HANDS.md) — identities
hold no browser state, no profiles, no credentials.

Permissions are FAIL-CLOSED: no grant = no action. `may()` returns False
for unknown identities, unknown actions, or missing grants.
"""

import json
import os
import re
import sqlite3
from datetime import datetime, timezone

DB_NAME = os.path.join("identity", "identities.db")

ACCOUNTS_DIR = os.path.join("identity", "accounts")
PERMS_DIR = os.path.join("identity", "permissions")

SCHEMA = """
CREATE TABLE IF NOT EXISTS identities (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, owner_name TEXT DEFAULT '',
    created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS identity_accounts (
    identity_id TEXT NOT NULL, account_label TEXT NOT NULL,
    platform TEXT NOT NULL, handle TEXT DEFAULT '',
    PRIMARY KEY (identity_id, account_label));
CREATE TABLE IF NOT EXISTS permissions (
    identity_id TEXT PRIMARY KEY, grants_json TEXT DEFAULT '{}',
    updated_at TEXT NOT NULL);
"""


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _slug(name):
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    if not slug:
        raise ValueError("identity name is required")
    return slug


def _connect(home):
    os.makedirs(os.path.join(home, "identity"), exist_ok=True)
    cx = sqlite3.connect(os.path.join(home, DB_NAME))
    cx.row_factory = sqlite3.Row
    cx.executescript(SCHEMA)
    return cx


def _write_json(home, subdir, name, data):
    d = os.path.join(home, subdir)
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, name + ".json")
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    os.replace(tmp, p)
    return p


# ------------------------------------------------------------ identities ---

def create_identity(home, name, owner_name=""):
    """Create a new persistent identity. Returns the identity record."""
    iid = _slug(name)
    cx = _connect(home)
    try:
        cx.execute(
            "INSERT INTO identities (id, name, owner_name, created_at)"
            " VALUES (?, ?, ?, ?)"
            " ON CONFLICT(id) DO UPDATE SET owner_name=excluded.owner_name",
            (iid, name, owner_name, utcnow()))
        cx.commit()
        row = cx.execute("SELECT * FROM identities WHERE id = ?",
                         (iid,)).fetchone()
    finally:
        cx.close()
    _write_json(home, ACCOUNTS_DIR, f"identity-{iid}",
                {"identity_id": iid, "name": name,
                 "owner_name": owner_name, "accounts": []})
    _write_json(home, PERMS_DIR, iid,
                {"identity_id": iid, "grants": {}, "updated_at": utcnow()})
    return dict(row)


def get_identity(home, identity_id):
    cx = _connect(home)
    try:
        row = cx.execute("SELECT * FROM identities WHERE id = ?",
                         (identity_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["accounts"] = [dict(r) for r in cx.execute(
            "SELECT account_label, platform, handle FROM identity_accounts"
            " WHERE identity_id = ? ORDER BY account_label", (identity_id,))]
        return d
    finally:
        cx.close()


def list_identities(home):
    cx = _connect(home)
    try:
        return [dict(r) for r in cx.execute(
            "SELECT * FROM identities ORDER BY id").fetchall()]
    finally:
        cx.close()


def link_account(home, identity_id, account_label, platform, handle=""):
    """Attach a social account to an identity (persona + permission scope)."""
    if get_identity(home, identity_id) is None:
        raise KeyError(f"unknown identity {identity_id!r}")
    cx = _connect(home)
    try:
        cx.execute(
            "INSERT INTO identity_accounts (identity_id, account_label,"
            " platform, handle) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(identity_id, account_label) DO UPDATE SET"
            " platform=excluded.platform, handle=excluded.handle",
            (identity_id, account_label, platform, handle))
        cx.commit()
    finally:
        cx.close()
    _write_json(home, ACCOUNTS_DIR, account_label,
                {"identity_id": identity_id, "label": account_label,
                 "platform": platform, "handle": handle,
                 "owner_name": get_identity(home, identity_id).get(
                     "owner_name", "")})
    return get_identity(home, identity_id)


def unlink_account(home, identity_id, account_label):
    cx = _connect(home)
    try:
        cx.execute(
            "DELETE FROM identity_accounts WHERE identity_id = ?"
            " AND account_label = ?", (identity_id, account_label))
        cx.commit()
    finally:
        cx.close()
    try:
        os.remove(os.path.join(home, ACCOUNTS_DIR, account_label + ".json"))
    except OSError:
        pass


def identity_for_account(home, account_label):
    """Which identity owns this account label? (None if unlinked)."""
    cx = _connect(home)
    try:
        row = cx.execute(
            "SELECT identity_id FROM identity_accounts"
            " WHERE account_label = ? LIMIT 1", (account_label,)).fetchone()
        return row["identity_id"] if row else None
    finally:
        cx.close()


# ------------------------------------------------------------ permissions ---

def _grants(home, identity_id):
    cx = _connect(home)
    try:
        row = cx.execute(
            "SELECT grants_json FROM permissions WHERE identity_id = ?",
            (identity_id,)).fetchone()
        return json.loads(row["grants_json"]) if row else {}
    finally:
        cx.close()


def set_permissions(home, identity_id, grants):
    """Replace the grant set for an identity (dict)."""
    if get_identity(home, identity_id) is None:
        raise KeyError(f"unknown identity {identity_id!r}")
    if not isinstance(grants, dict):
        raise ValueError("grants must be a dict")
    cx = _connect(home)
    try:
        cx.execute(
            "INSERT INTO permissions (identity_id, grants_json, updated_at)"
            " VALUES (?, ?, ?)"
            " ON CONFLICT(identity_id) DO UPDATE SET"
            " grants_json=excluded.grants_json,"
            " updated_at=excluded.updated_at",
            (identity_id, json.dumps(grants), utcnow()))
        cx.commit()
    finally:
        cx.close()
    _write_json(home, PERMS_DIR, identity_id,
                {"identity_id": identity_id, "grants": grants,
                 "updated_at": utcnow()})
    return grants


def grant(home, identity_id, action):
    """Grant one action to an identity."""
    grants = _grants(home, identity_id)
    actions = set(grants.get("actions", []))
    actions.add(action)
    grants["actions"] = sorted(actions)
    return set_permissions(home, identity_id, grants)


def revoke(home, identity_id, action):
    """Revoke one action from an identity."""
    grants = _grants(home, identity_id)
    actions = set(grants.get("actions", []))
    actions.discard(action)
    grants["actions"] = sorted(actions)
    return set_permissions(home, identity_id, grants)


def may(home, identity_id, action):
    """Fail-closed permission check: no grant = no action."""
    if get_identity(home, identity_id) is None:
        return False
    grants = _grants(home, identity_id)
    actions = grants.get("actions", [])
    return bool(action) and (action in actions or "*" in actions)


def approval_required(home, identity_id, action):
    """Does this action need human approval for this identity?

    Default is True (fail-closed): only actions explicitly listed under
    grants.require_approval_exempt skip the queue."""
    grants = _grants(home, identity_id)
    exempt = set(grants.get("require_approval_exempt", []))
    return action not in exempt


def get_permissions(home, identity_id):
    return _grants(home, identity_id)
