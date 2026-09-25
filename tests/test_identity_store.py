"""v10: identity store — multiple persistent social identities.

identity/
  accounts/          per-account files (handle, platform, persona, owner)
  permissions/       per-identity grants (fail-closed: no grant = no action)
  identities.db      SQLite registry tying it together

Identities hold personas, account mappings, and permissions. Execution
happens in the agent's browser via hands tickets — identities keep no
browser state, no profiles, no credentials.
"""

import json
import os

import pytest

from identity import store as ids


def test_create_and_list_identities(home):
    i = ids.create_identity(home, "Nova", owner_name="Ochacho")
    assert i["id"] == "nova"
    assert i["owner_name"] == "Ochacho"
    assert [x["id"] for x in ids.list_identities(home)] == ["nova"]
    # re-creating updates, never duplicates
    ids.create_identity(home, "Nova", owner_name="Ochacho")
    assert len(ids.list_identities(home)) == 1


def test_link_account_maps_accounts_to_identity(home):
    ids.create_identity(home, "Nova")
    ids.link_account(home, "nova", "tt-main", "tiktok", handle="@nova")
    ids.link_account(home, "nova", "x-main", "x", handle="@nova_x")
    ident = ids.get_identity(home, "nova")
    labels = {a["account_label"] for a in ident["accounts"]}
    assert labels == {"tt-main", "x-main"}
    # per-account files are human-readable JSON on disk
    acct = json.load(open(os.path.join(
        home, "identity", "accounts", "tt-main.json")))
    assert acct["identity_id"] == "nova"
    assert acct["handle"] == "@nova"
    assert ids.identity_for_account(home, "tt-main") == "nova"
    assert ids.identity_for_account(home, "stranger") is None
    # unlinking removes the mapping and the account file
    ids.unlink_account(home, "nova", "x-main")
    assert ids.identity_for_account(home, "x-main") is None
    assert not os.path.exists(os.path.join(
        home, "identity", "accounts", "x-main.json"))


def test_permissions_fail_closed(home):
    ids.create_identity(home, "Nova")
    # unknown identity: denied
    assert ids.may(home, "ghost", "like") is False
    # known identity, no grants: denied (fail-closed)
    assert ids.may(home, "nova", "like") is False
    # empty action: denied
    assert ids.may(home, "nova", "") is False
    ids.grant(home, "nova", "like")
    assert ids.may(home, "nova", "like") is True
    assert ids.may(home, "nova", "comment") is False  # not granted
    ids.revoke(home, "nova", "like")
    assert ids.may(home, "nova", "like") is False
    # wildcard grant
    ids.set_permissions(home, "nova", {"actions": ["*"]})
    assert ids.may(home, "nova", "anything") is True


def test_approval_required_defaults_to_yes(home):
    ids.create_identity(home, "Nova")
    # fail-closed: approval required unless explicitly exempted
    assert ids.approval_required(home, "nova", "publish") is True
    ids.set_permissions(home, "nova",
                        {"actions": ["like"],
                         "require_approval_exempt": ["like"]})
    assert ids.approval_required(home, "nova", "like") is False
    assert ids.approval_required(home, "nova", "publish") is True
    # permission files are human-readable JSON on disk
    perms = json.load(open(os.path.join(
        home, "identity", "permissions", "nova.json")))
    assert perms["grants"]["actions"] == ["like"]


def test_link_unknown_identity_refused(home):
    with pytest.raises(KeyError):
        ids.link_account(home, "ghost", "a1", "tiktok")
    with pytest.raises(KeyError):
        ids.grant(home, "ghost", "like")
