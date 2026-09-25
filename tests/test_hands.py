"""Tests for the hands execution-ticket interface (no browser engine)."""

import json
import os

import pytest

from hands import tickets as hands_mod
from platforms import tos as tos_mod


def _policy(**over):
    p = {"rate_limits": {"default": {"actions_per_hour": 1000,
                                     "actions_per_day": 10000}},
         "quiet_hours": {"enabled": False},
         "tos": {"acknowledged_risk": []}}
    p.update(over)
    return p


def test_ticket_create_and_fulfill(home):
    t = hands_mod.create_ticket(home, "tiktok", "main", "like",
                                params={"target_url": "https://tiktok.com/x"},
                                policy=_policy())
    assert t["status"] == "open"
    assert t["ticket_id"].startswith("t-")
    assert t["receipts"]["tos"]["acknowledged_risk"] is False
    path = os.path.join(home, "hands", "tickets", t["ticket_id"] + ".json")
    assert os.path.exists(path)
    # instructions are agent-readable
    assert "tiktok" in t["instructions"] and "main" in t["instructions"]

    got = hands_mod.get_ticket(home, t["ticket_id"])
    assert got["ticket_id"] == t["ticket_id"]
    items = hands_mod.list_tickets(home, status="open")
    assert any(i["ticket_id"] == t["ticket_id"] for i in items)

    done = hands_mod.fulfill_ticket(home, t["ticket_id"], result="liked it")
    assert done["status"] == "fulfilled"
    assert done["result"] == "liked it"
    assert hands_mod.list_tickets(home, status="open") == []


def test_ticket_fulfill_is_idempotent_safe(home):
    t = hands_mod.create_ticket(home, "tiktok", "main", "like",
                                params={"target_url": "https://tiktok.com/x"},
                                policy=_policy())
    hands_mod.fulfill_ticket(home, t["ticket_id"], result="done")
    with pytest.raises(hands_mod.TicketRefused):
        hands_mod.fulfill_ticket(home, t["ticket_id"], result="again")
    with pytest.raises(hands_mod.TicketRefused):
        hands_mod.cancel_ticket(home, t["ticket_id"])


def test_ticket_cancel(home):
    t = hands_mod.create_ticket(home, "instagram", "main", "follow",
                                params={"target_url": "https://ig/x"},
                                policy=_policy())
    c = hands_mod.cancel_ticket(home, t["ticket_id"], reason="changed mind")
    assert c["status"] == "cancelled"
    assert c["cancel_reason"] == "changed mind"


def test_ticket_unknown_action_refused(home):
    with pytest.raises(hands_mod.TicketRefused):
        hands_mod.create_ticket(home, "tiktok", "main", "nuke",
                                policy=_policy())


def test_ticket_tos_prohibited_refused_without_ack(home):
    # X automated likes are prohibited by the ToS layer.
    with pytest.raises(hands_mod.TicketRefused) as ei:
        hands_mod.create_ticket(home, "x", "main", "like",
                                params={"target_url": "https://x.com/x"},
                                policy=_policy())
    assert "ToS" in str(ei.value)


def test_ticket_tos_proceeds_with_acknowledged_risk(home, capsys):
    pol = _policy(tos={"acknowledged_risk": ["x"]})
    t = hands_mod.create_ticket(home, "x", "main", "like",
                                params={"target_url": "https://x.com/x"},
                                policy=pol)
    assert t["receipts"]["tos"]["acknowledged_risk"] is True


def test_ticket_crisis_refuses(home):
    from crisis import mode as crisis_mod
    crisis_mod.activate(home, reason="test")
    try:
        with pytest.raises(hands_mod.TicketRefused) as ei:
            hands_mod.create_ticket(home, "tiktok", "main", "like",
                                    params={"target_url": "https://t/x"},
                                    policy=_policy())
        assert "crisis" in str(ei.value).lower()
    finally:
        crisis_mod.deactivate(home)


def test_ticket_rate_limit_consumes_bucket(home):
    pol = _policy(rate_limits={"default": {"actions_per_hour": 1,
                                           "actions_per_day": 1}})
    hands_mod.create_ticket(home, "tiktok", "main", "like",
                            params={"target_url": "https://t/1"}, policy=pol)
    with pytest.raises(hands_mod.TicketRefused):
        hands_mod.create_ticket(home, "tiktok", "main", "like",
                                params={"target_url": "https://t/2"},
                                policy=pol)


def test_ticket_quiet_hours_refuses(home):
    pol = _policy(quiet_hours={"enabled": True, "start": "00:00",
                               "end": "23:59"})
    with pytest.raises(hands_mod.TicketRefused) as ei:
        hands_mod.create_ticket(home, "tiktok", "main", "like",
                                params={"target_url": "https://t/x"},
                                policy=pol)
    assert "quiet hours" in str(ei.value)


def test_ticket_approval_link_must_be_approved(home):
    from approvals import queue as q
    item = q.propose(home, "like", "tiktok", "main", "like this",
                     payload={})
    with pytest.raises(hands_mod.TicketRefused):
        hands_mod.create_ticket(home, "tiktok", "main", "like",
                                params={"target_url": "https://t/x"},
                                policy=_policy(), approval_id=item["id"])
    q.approve(home, item["id"])
    t = hands_mod.create_ticket(home, "tiktok", "main", "like",
                                params={"target_url": "https://t/x"},
                                policy=_policy(), approval_id=item["id"])
    assert t["receipts"]["approval_id"] == item["id"]


def test_ticket_unknown_returns_none(home):
    assert hands_mod.get_ticket(home, "t-nope") is None
    assert hands_mod.list_tickets(home) == []
