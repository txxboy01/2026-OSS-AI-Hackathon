from itertools import combinations

import pytest

from app.constants import USER_ACTION_ORDER
from app.guidance import get_guidance


@pytest.mark.parametrize(
    "action,expected,urgency",
    [
        ("NOT_INTERACTED", ["G_STOP", "G_VERIFY"], "routine"),
        ("OPENED_LINK", ["G_STOP", "G_CLOSE", "G_VERIFY"], "prompt"),
        ("SUBMITTED_CREDENTIALS", ["G_STOP", "G_PASSWORD", "G_SESSIONS", "G_VERIFY"], "prompt"),
        ("SUBMITTED_PERSONAL", ["G_STOP", "G_PRIVACY", "G_VERIFY"], "prompt"),
        ("SENT_MONEY", ["G_BANK", "G_STOP", "G_VERIFY", "G_HELP"], "urgent"),
        ("INSTALLED_APP", ["G_DEVICE", "G_STOP", "G_VERIFY", "G_HELP"], "urgent"),
        ("UNKNOWN", ["G_STOP", "G_VERIFY", "G_HELP"], "prompt"),
    ],
)
def test_independent_guidance(client, action, expected, urgency):
    c, fake = client
    result = c.post("/guidance", json={"actions": [action]})
    assert result.status_code == 200
    data = result.json()
    assert [s["code"] for s in data["steps"]] == expected
    assert data["urgency"] == urgency and fake.calls == 0


ACTIVE = ["OPENED_LINK", "SUBMITTED_CREDENTIALS", "SUBMITTED_PERSONAL", "SENT_MONEY", "INSTALLED_APP"]
COMBINATIONS = [list(c) for size in range(1, 6) for c in combinations(ACTIVE, size)]


@pytest.mark.parametrize("actions", COMBINATIONS)
def test_every_valid_multi_action_order(actions):
    a = get_guidance(actions, "request")
    b = get_guidance(list(reversed(actions)), "request")
    assert a == b
    assert a.actions == sorted(actions, key=USER_ACTION_ORDER.index)
    assert len(a.steps) == len({s.code for s in a.steps})
    assert [s.priority for s in a.steps] == sorted(s.priority for s in a.steps)
    if "INSTALLED_APP" in actions:
        assert a.steps[0].code == "G_DEVICE"
    assert a.urgency == ("urgent" if {"SENT_MONEY", "INSTALLED_APP"} & set(actions) else "prompt")


@pytest.mark.parametrize(
    "actions",
    [
        [],
        ["BOGUS"],
        ["UNKNOWN", "OPENED_LINK"],
        ["NOT_INTERACTED", "UNKNOWN"],
        ["NOT_INTERACTED", "SENT_MONEY"],
        ["OPENED_LINK", "OPENED_LINK"],
        "UNKNOWN",
        [True],
    ],
)
def test_invalid_guidance(client, actions):
    c, fake = client
    response = c.post("/guidance", json={"actions": actions})
    assert response.status_code == 422 and response.json()["error"]["code"] == "INVALID_REQUEST"
    assert fake.calls == 0
