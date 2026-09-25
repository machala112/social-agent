"""hands: execution tickets for the external agent browser.

The Playwright browser engine is gone. social-agent never drives a
browser itself anymore. When an approved action is ready to be
performed, the CLI emits an *execution ticket* — a machine-readable
JSON document describing exactly what must be done. An external agent
(e.g. Muse's server-side Chromium, watched live in the browser card)
fulfills the ticket, and the operator closes the loop with
``hands ticket fulfill``.

Guard order on ticket creation (same as the old acting guard):
    ToS > crisis > approvals > rate limits > quiet hours

Tickets live at ``<home>/hands/tickets/<ticket_id>.json``.
"""

import json
import os
import time
import uuid
from datetime import datetime, timezone

from platforms import tos as tos_mod
from crisis import mode as crisis_mod
from ratelimit import controller as rl_controller
from approvals import queue as approvals_queue

# Action names the hands interface accepts. Each maps onto a ToS action
# class (kept identical to the old browser backend's mapping).
TICKET_ACTIONS = (
    "like", "comment", "follow", "unfollow", "follow_user",
    "unfollow_user", "post_text", "post_video", "post_photo",
    "upload_video", "dm_send", "hide_comment", "subscribe",
)

ACTION_TO_TOS_CLASS = {
    "like": "like", "comment": "comment", "follow": "follow",
    "unfollow": "follow", "follow_user": "follow",
    "unfollow_user": "follow", "post_text": "post",
    "post_video": "post", "post_photo": "post", "upload_video": "post",
    "dm_send": "dm", "hide_comment": "hide", "subscribe": "follow",
}

STATUSES = ("open", "fulfilled", "cancelled")


class TicketRefused(Exception):
    """A guard layer refused to issue the ticket (fail closed)."""


def ticket_dir(home):
    d = os.path.join(home, "hands", "tickets")
    os.makedirs(d, exist_ok=True)
    return d


def _utcnow():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_id():
    return "t-" + uuid.uuid4().hex[:12]


def _in_quiet_hours(policy, now=None):
    qh = (policy or {}).get("quiet_hours") or {}
    if not qh.get("enabled"):
        return False
    now = now or datetime.now().astimezone()
    s, e = qh.get("start", "22:00"), qh.get("end", "08:00")
    cur = now.strftime("%H:%M")
    if s <= e:
        return s <= cur < e
    return cur >= s or cur < e


def _instructions(platform, account_label, action, params):
    """Plain-language steps the fulfilling agent follows in its browser."""
    target = params.get("target_url") or params.get("thread_url") or ""
    lines = [
        f"In the agent browser, signed in to {platform} as account "
        f"'{account_label}':",
    ]
    if action == "like":
        lines.append(f"1. Open {target}")
        lines.append("2. Click the Like button on that post.")
    elif action == "comment":
        lines.append(f"1. Open {target}")
        lines.append(f"2. Reply with exactly: {params.get('text', '')!r}")
    elif action in ("follow", "follow_user"):
        lines.append(f"1. Open the profile {target}")
        lines.append("2. Click Follow.")
    elif action in ("unfollow", "unfollow_user"):
        lines.append(f"1. Open the profile {target}")
        lines.append("2. Unfollow.")
    elif action == "post_text":
        lines.append("1. Open the post composer.")
        lines.append(f"2. Post exactly: {params.get('text', '')!r}")
    elif action in ("post_video", "upload_video"):
        lines.append("1. Open the video upload flow.")
        lines.append(f"2. Upload {params.get('video_path', params.get('file', ''))!r}")
        if params.get("title"):
            lines.append(f"3. Title/caption: {params['title']!r}")
    elif action == "post_photo":
        lines.append("1. Open the photo upload flow.")
        lines.append(f"2. Upload {params.get('photo_path', params.get('file', ''))!r}")
    elif action == "dm_send":
        lines.append(f"1. Open the DM thread {target}")
        lines.append(f"2. Send exactly: {params.get('text', '')!r}")
    elif action == "hide_comment":
        lines.append(f"1. Open {target}")
        lines.append("2. Hide the flagged comment (your own post only).")
    elif action == "subscribe":
        lines.append(f"1. Open the channel {target}")
        lines.append("2. Subscribe.")
    else:
        lines.append(f"Perform {action} with params: {params!r}")
    lines.append("3. Report what you did so the operator can fulfill the ticket.")
    return "\n".join(lines)


def create_ticket(home, platform, account_label, action, params=None,
                  policy=None, approval_id=None):
    """Issue an execution ticket after the full guard order passes.

    Raises TicketRefused (fail closed) when any layer denies:
      1. ToS (platforms/tos.py, incl. acknowledged_risk opt-in)
      2. crisis mode (global kill switch)
      3. approvals (when approval_id is given it must be approved)
      4. rate limits (denial queues with retry; never dropped)
      5. quiet hours

    Returns the ticket dict; also writes it to hands/tickets/<id>.json.
    """
    policy = policy or {}
    params = params or {}
    platform = (platform or "").lower()
    if action not in TICKET_ACTIONS:
        raise TicketRefused(f"unknown hands action {action!r}"
                            f" (available: {sorted(TICKET_ACTIONS)})")

    # 1. ToS FIRST — fail closed unless the risk was acknowledged.
    tos_class = tos_mod.CLI_OP_TO_CLASS.get(
        ACTION_TO_TOS_CLASS.get(action, action))
    if tos_class is None:
        raise TicketRefused(f"no ToS classification for hands action"
                            f" {action!r}; refusing by default")
    try:
        rule = tos_mod.check_tos(platform, tos_class, policy=policy, home=home)
    except tos_mod.ToSRefusal as e:
        raise TicketRefused(f"ToS: {e}")

    # 2. Crisis kill switch.
    try:
        crisis_mod.check(home)
    except crisis_mod.CrisisActive as e:
        raise TicketRefused(f"crisis: {e}")

    # 3. Approvals — when an approval is linked, it must be approved.
    approval_receipt = None
    if approval_id:
        item = approvals_queue.get(home, approval_id)
        if item is None:
            raise TicketRefused(f"approval {approval_id!r} not found")
        if item.get("status") != "approved":
            raise TicketRefused(
                f"approval {approval_id!r} is {item.get('status')!r},"
                f" not approved")
        approval_receipt = approval_id

    # 4. Rate limits — denial raises (the CLI maps it to a queued retry).
    verdict = rl_controller.check(home, platform, action, policy)
    if not verdict.get("allowed"):
        raise TicketRefused(
            verdict.get("reason") or "rate limit reached; retry later")
    rl_controller.consume(home, platform, action)

    # 5. Quiet hours.
    if _in_quiet_hours(policy):
        raise TicketRefused("quiet hours active: acting operations are paused")

    ticket_id = _new_id()
    ticket = {
        "ticket_id": ticket_id,
        "idempotency_key": ticket_id,
        "created_at": _utcnow(),
        "created_at_ts": time.time(),
        "platform": platform,
        "account_label": account_label,
        "action": action,
        "params": params,
        "receipts": {
            "tos": {"status": rule.get("status"),
                    "acknowledged_risk": bool(rule.get("acknowledged_risk"))},
            "approval_id": approval_receipt,
            "rate_limit": {"remaining_hour": verdict.get("remaining_hour"),
                           "remaining_day": verdict.get("remaining_day")},
            "quiet_hours": False,
        },
        "instructions": _instructions(platform, account_label, action, params),
        "status": "open",
        "fulfilled_at": None,
        "result": None,
        "cancelled_at": None,
        "cancel_reason": None,
    }
    path = os.path.join(ticket_dir(home), ticket_id + ".json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(ticket, fh, indent=2)
    os.replace(tmp, path)
    return ticket


def get_ticket(home, ticket_id):
    path = os.path.join(ticket_dir(home), ticket_id + ".json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def list_tickets(home, status=None):
    out = []
    d = os.path.join(home, "hands", "tickets")
    if not os.path.isdir(d):
        return out
    for name in sorted(os.listdir(d)):
        if not name.endswith(".json"):
            continue
        with open(os.path.join(d, name), encoding="utf-8") as fh:
            try:
                t = json.load(fh)
            except ValueError:
                continue
        if status and t.get("status") != status:
            continue
        out.append(t)
    return out


def _save(home, ticket):
    path = os.path.join(ticket_dir(home), ticket["ticket_id"] + ".json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(ticket, fh, indent=2)
    os.replace(tmp, path)


def fulfill_ticket(home, ticket_id, result=""):
    """Close the loop after the agent performed the ticket. Idempotent-safe:
    fulfilling a non-open ticket is refused, never double-counted."""
    t = get_ticket(home, ticket_id)
    if t is None:
        raise TicketRefused(f"ticket {ticket_id!r} not found")
    if t.get("status") != "open":
        raise TicketRefused(f"ticket {ticket_id!r} is already"
                            f" {t.get('status')!r}; refusing duplicate")
    t["status"] = "fulfilled"
    t["fulfilled_at"] = _utcnow()
    t["result"] = result or "performed by the agent browser"
    _save(home, t)
    return t


def cancel_ticket(home, ticket_id, reason=""):
    t = get_ticket(home, ticket_id)
    if t is None:
        raise TicketRefused(f"ticket {ticket_id!r} not found")
    if t.get("status") != "open":
        raise TicketRefused(f"ticket {ticket_id!r} is already"
                            f" {t.get('status')!r}")
    t["status"] = "cancelled"
    t["cancelled_at"] = _utcnow()
    t["cancel_reason"] = reason
    _save(home, t)
    return t
