"""The mock ERP store: pricing, requisitions, tenancy and approval enforcement."""

import pytest

from agentic_solutions.common.approval_tokens import issue
from agentic_solutions.mcp_servers.erp import policy
from agentic_solutions.mcp_servers.erp.config import ErpSettings
from agentic_solutions.mcp_servers.erp.store import ErpError, ErpStore

SECRET = b"test-erp-secret"
LIMIT = 5000.0
T0 = 1_800_000_000.0


class Clock:
    def __init__(self, t: float = T0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def db(tmp_path):
    return str(tmp_path / "nested" / "erp.sqlite")


@pytest.fixture
def store(db, clock):
    s = ErpStore(db, secret=SECRET, auto_limit_zar=LIMIT, tenant_ttl_hours=168, clock=clock)
    yield s
    s.close()


def first_sku(store, tenant, category):
    return store.search_catalogue(tenant, "", category=category)[0]["sku"]


def draft(store, tenant, category, quantity, cost_centre):
    sku = first_sku(store, tenant, category)
    quote = store.get_price_quote(tenant, sku, quantity)
    return store.create_requisition(tenant, cost_centre, [{"quote_id": quote["quote_id"]}], "Team refresh")


def token_for(req, tenant, clock, *, approver="visitor:0123456789ab", secret=SECRET, ttl_s=900, **over):
    claims = {
        "req_id": req["req_id"],
        "version": req["version"],
        "content_hash": req["content_hash"],
        "tenant": tenant,
        "approver": approver,
        "requested_by": "agent",
        "reason": "approved" if approver != "policy" else "under limit",
        **over,
    }
    return issue(claims, secret, ttl_s=ttl_s, now=clock())


def submit(store, tenant, req, token, key=None):
    return store.submit_purchase_order(
        tenant, req["req_id"], req["version"], token, key or f"{req['req_id']}:{req['version']}"
    )


def events(store, tenant, req_id):
    return [e["event"] for e in store.get_audit_trail(tenant, req_id)]


# ---------------------------------------------------------------- policy, config


def test_policy_threshold_and_reason():
    assert policy.needs_person(5000.01, 5000) is True
    assert policy.needs_person(5000, 5000) is False
    assert policy.reason(12000, 5000) == "Over R5,000 needs approval"
    assert policy.reason(3000, 5000) == "Under R5,000: approved by policy"
    assert policy.reason(5000, 5000) == "Under R5,000: approved by policy"


def test_settings_defaults_and_env(monkeypatch):
    for var in ("ERP_DB", "ERP_APPROVAL_SECRET", "ERP_AUTO_APPROVE_LIMIT_ZAR", "ERP_TENANT_TTL_HOURS",
                "ERP_HOST", "ERP_PORT"):
        monkeypatch.delenv(var, raising=False)
    s = ErpSettings.from_env()
    assert (s.db, s.auto_limit_zar, s.tenant_ttl_hours, s.host, s.port) == (
        "./data/erp.sqlite", 5000.0, 168.0, "127.0.0.1", 8765)
    assert isinstance(s.secret, bytes) and len(s.secret) >= 32
    assert ErpSettings.from_env().secret != s.secret  # random per start
    monkeypatch.setenv("ERP_APPROVAL_SECRET", "shared")
    monkeypatch.setenv("ERP_AUTO_APPROVE_LIMIT_ZAR", "7500")
    monkeypatch.setenv("ERP_TENANT_TTL_HOURS", "24")
    s = ErpSettings.from_env()
    assert (s.secret, s.auto_limit_zar, s.tenant_ttl_hours) == (b"shared", 7500.0, 24.0)


# ---------------------------------------------------------------- fixtures, pricing


def test_fixtures_cover_samples(store):
    t = "tenant-a"
    for cat in ("laptops", "monitors", "docking stations", "keyboards", "mice", "chairs", "desks",
                "network gear"):
        assert store.search_catalogue(t, "", category=cat), cat
    ct_ops = store.check_budget(t, "CT-OPS")["remaining"]
    jhb_fin = store.check_budget(t, "JHB-FIN")["remaining"]
    # Every laptop, keyboard and monitor routes the same way, whichever one the agent picks.
    for item in store.search_catalogue(t, "laptops"):
        total = store.get_price_quote(t, item["sku"], 12)["line_total_zar"]
        assert policy.needs_person(total, LIMIT) and total <= ct_ops, item
    keyboards = store.search_catalogue(t, "keyboards")
    assert keyboards
    for item in keyboards:
        total = store.get_price_quote(t, item["sku"], 3)["line_total_zar"]
        assert not policy.needs_person(total, LIMIT), item
    monitors = store.search_catalogue(t, "monitors")
    assert monitors
    for item in monitors:
        total = store.get_price_quote(t, item["sku"], 40)["line_total_zar"]
        assert policy.needs_person(total, LIMIT) and total > jhb_fin, item


def test_catalogue_suppliers_and_budgets(store):
    t = "tenant-a"
    items = store.search_catalogue(t, "")
    assert len(items) == 10  # capped
    assert set(items[0]) == {"sku", "name", "unit_price_zar", "supplier_id", "category"}
    cheap = store.search_catalogue(t, "", category="keyboards", max_unit_price=600)
    assert cheap and all(i["unit_price_zar"] <= 600 and i["category"] == "keyboards" for i in cheap)
    assert store.search_catalogue(t, "laptop") == store.search_catalogue(t, "laptops")
    supplier = store.get_supplier(t, items[0]["supplier_id"])
    assert {"supplier_id", "name", "lead_time_days", "rating", "preferred"} <= set(supplier)
    for cc in ("CT-OPS", "JHB-FIN", "DBN-LOG", "HQ-IT"):
        b = store.check_budget(t, cc)
        assert b["remaining"] == b["allocated"] - b["committed"]
    with pytest.raises(ErpError) as e:
        store.get_supplier(t, "SUP-NOPE")
    assert e.value.code == "not_found"
    with pytest.raises(ErpError) as e:
        store.check_budget(t, "XX-NOPE")
    assert e.value.code == "not_found"


def test_quote_discounts_rounding_and_expiry(store, clock):
    t = "tenant-a"
    sku = first_sku(store, t, "laptops")
    base = store.search_catalogue(t, sku)[0]["unit_price_zar"]
    q1 = store.get_price_quote(t, sku, 9)
    q10 = store.get_price_quote(t, sku, 10)
    q50 = store.get_price_quote(t, sku, 50)
    assert q1["unit_price_zar"] == base
    assert q10["unit_price_zar"] == round(base * 0.95)
    assert q50["unit_price_zar"] == round(base * 0.90)
    assert q10["line_total_zar"] == q10["unit_price_zar"] * 10
    assert all(isinstance(q["line_total_zar"], int) for q in (q1, q10, q50))
    assert q1["quote_id"] != q10["quote_id"]
    assert q1["expires_at_ts"] == clock() + 1800
    # Deterministic prices: a second quote prices the same.
    assert store.get_price_quote(t, sku, 10)["unit_price_zar"] == q10["unit_price_zar"]
    for bad in (0, -1, 1000, 2.5, "3"):
        with pytest.raises(ErpError) as e:
            store.get_price_quote(t, sku, bad)
        assert e.value.code == "invalid"
    with pytest.raises(ErpError) as e:
        store.get_price_quote(t, "NOPE-1", 1)
    assert e.value.code == "not_found"


def test_requisition_shape_and_hash(store):
    t = "tenant-a"
    req = draft(store, t, "keyboards", 3, "CT-OPS")
    assert req["version"] == 1 and req["status"] == "draft"
    assert {"req_id", "version", "cost_centre", "justification", "total_zar", "content_hash",
            "status", "lines"} <= set(req)
    line = req["lines"][0]
    assert {"sku", "name", "quantity", "unit_price_zar", "line_total_zar", "quote_id",
            "quote_expires_at"} <= set(line)
    assert req["total_zar"] == line["line_total_zar"]
    assert len(req["content_hash"]) == 64
    assert store.get_requisition(t, req["req_id"]) == req


def test_create_requisition_validation(store, clock):
    t = "tenant-a"
    sku = first_sku(store, t, "keyboards")
    q = store.get_price_quote(t, sku, 2)
    cases = [
        ("NO-CC", [{"quote_id": q["quote_id"]}], "x", "not_found"),
        ("CT-OPS", [], "x", "invalid"),
        ("CT-OPS", [{"quote_id": "Q-9999"}], "x", "not_found"),
        ("CT-OPS", [{"quote_id": q["quote_id"]}, {"quote_id": q["quote_id"]}], "x", "invalid"),
    ]
    for cc, lines, just, code in cases:
        with pytest.raises(ErpError) as e:
            store.create_requisition(t, cc, lines, just)
        assert e.value.code == code, (cc, lines)
    with pytest.raises(ErpError) as e:
        store.create_requisition("tenant-b", "CT-OPS", [{"quote_id": q["quote_id"]}], "x")
    assert e.value.code == "not_found"  # another tenant's quote
    clock.advance(1801)
    with pytest.raises(ErpError) as e:
        store.create_requisition(t, "CT-OPS", [{"quote_id": q["quote_id"]}], "x")
    assert e.value.code == "expired"


# ---------------------------------------------------------------- submit


def test_valid_token_submits_and_commits_budget(store, clock):
    t = "tenant-a"
    before = store.check_budget(t, "CT-OPS")
    req = draft(store, t, "laptops", 12, "CT-OPS")
    po = submit(store, t, req, token_for(req, t, clock))
    assert po["po_number"] == "PO-0001" and po["status"] == "ordered"
    after = store.check_budget(t, "CT-OPS")
    assert after["committed"] == before["committed"] + req["total_zar"]
    assert after["remaining"] == before["remaining"] - req["total_zar"]
    got = store.get_requisition(t, req["req_id"])
    assert got["status"] == "ordered" and got["po_number"] == "PO-0001"
    assert events(store, t, req["req_id"])[-1] == "submitted"


def _tampered(req, t, clock):
    tok = token_for(req, t, clock)
    payload, sig = tok.split(".")
    return f"{payload}.{'A' if sig[0] != 'A' else 'B'}{sig[1:]}"


REFUSALS = {
    "tampered signature": (_tampered, "Invalid approval."),
    "wrong secret": (lambda r, t, c: token_for(r, t, c, secret=b"other"), "Invalid approval."),
    "garbage": (lambda r, t, c: "not-a-token", "Invalid approval."),
    "wrong version": (lambda r, t, c: token_for(r, t, c, version=r["version"] + 1),
                      "The approval does not match this request (it was changed after approval)."),
    "wrong hash": (lambda r, t, c: token_for(r, t, c, content_hash="0" * 64),
                   "The approval does not match this request (it was changed after approval)."),
    "wrong req": (lambda r, t, c: token_for(r, t, c, req_id="REQ-9999"),
                  "The approval does not match this request (it was changed after approval)."),
    "wrong tenant": (lambda r, t, c: token_for(r, "tenant-b", c),
                     "The approval does not match this request (it was changed after approval)."),
    "approver is requester": (lambda r, t, c: token_for(r, t, c, approver="agent"), "Invalid approval."),
    "policy token over limit": (lambda r, t, c: token_for(r, t, c, approver="policy"),
                                "Policy cannot approve orders over R5,000."),
}


@pytest.mark.parametrize("case", list(REFUSALS))
def test_token_refusals_are_audited(store, clock, case):
    t = "tenant-a"
    before = store.check_budget(t, "CT-OPS")
    req = draft(store, t, "laptops", 12, "CT-OPS")
    make, reason = REFUSALS[case]
    with pytest.raises(ErpError) as e:
        submit(store, t, req, make(req, t, clock))
    assert e.value.code == "refused"
    assert str(e.value) == reason
    trail = store.get_audit_trail(t, req["req_id"])
    assert trail[-1]["event"] == "refused" and trail[-1]["detail"] == reason
    assert store.check_budget(t, "CT-OPS") == before
    assert store.get_requisition(t, req["req_id"])["status"] == "draft"


def test_expired_token_refused(store, clock):
    t = "tenant-a"
    req = draft(store, t, "laptops", 12, "CT-OPS")
    tok = token_for(req, t, clock, ttl_s=60)
    clock.advance(61)
    with pytest.raises(ErpError) as e:
        submit(store, t, req, tok)
    assert e.value.code == "refused" and str(e.value) == "The approval has expired."
    assert store.get_audit_trail(t, req["req_id"])[-1]["detail"] == "The approval has expired."


def test_wrong_version_argument_refused(store, clock):
    t = "tenant-a"
    req = draft(store, t, "laptops", 12, "CT-OPS")
    with pytest.raises(ErpError) as e:
        store.submit_purchase_order(t, req["req_id"], 2, token_for(req, t, clock), "k")
    assert e.value.code == "refused"
    assert "changed after approval" in str(e.value)


def test_policy_token_under_limit_submits(store, clock):
    t = "tenant-a"
    req = draft(store, t, "keyboards", 3, "CT-OPS")
    po = submit(store, t, req, token_for(req, t, clock, approver="policy"))
    assert po["status"] == "ordered"


def test_expired_quote_refused(store, clock):
    t = "tenant-a"
    req = draft(store, t, "laptops", 12, "CT-OPS")
    clock.advance(1801)
    with pytest.raises(ErpError) as e:
        submit(store, t, req, token_for(req, t, clock))
    assert e.value.code == "refused"
    assert str(e.value) == "A price quote has expired. Ask for a new quote."
    assert events(store, t, req["req_id"])[-1] == "refused"


def test_overspend_refused_at_submit(store, clock):
    t = "tenant-a"
    first = draft(store, t, "laptops", 12, "CT-OPS")
    second = draft(store, t, "laptops", 12, "CT-OPS")
    remaining = store.check_budget(t, "CT-OPS")["remaining"]
    assert first["total_zar"] <= remaining and first["total_zar"] + second["total_zar"] > remaining
    tok_second = token_for(second, t, clock)  # approved while the budget still covered it
    submit(store, t, first, token_for(first, t, clock))
    left = store.check_budget(t, "CT-OPS")["remaining"]
    with pytest.raises(ErpError) as e:
        submit(store, t, second, tok_second)
    expected = (f"Over budget: R{second['total_zar']:,} needed, R{left:,} remaining in CT-OPS.")
    assert str(e.value) == expected
    assert store.get_audit_trail(t, second["req_id"])[-1]["detail"] == expected
    assert store.check_budget(t, "CT-OPS")["remaining"] == left


def test_monitor_sample_refused_over_budget(store, clock):
    t = "tenant-a"
    req = draft(store, t, "monitors", 40, "JHB-FIN")
    with pytest.raises(ErpError) as e:
        submit(store, t, req, token_for(req, t, clock))
    assert str(e.value).startswith("Over budget: R")
    assert str(e.value).endswith("remaining in JHB-FIN.")


def test_idempotent_submit_same_key_same_po_no_double_commit(store, clock):
    t = "tenant-a"
    req = draft(store, t, "laptops", 12, "CT-OPS")
    tok = token_for(req, t, clock)
    po1 = submit(store, t, req, tok, key="k-1")
    budget = store.check_budget(t, "CT-OPS")
    po2 = submit(store, t, req, tok, key="k-1")
    assert po1 == po2
    assert store.check_budget(t, "CT-OPS") == budget
    assert events(store, t, req["req_id"]).count("submitted") == 1


def test_second_submit_different_key_refused(store, clock):
    t = "tenant-a"
    req = draft(store, t, "laptops", 12, "CT-OPS")
    tok = token_for(req, t, clock)
    submit(store, t, req, tok, key="k-1")
    budget = store.check_budget(t, "CT-OPS")
    with pytest.raises(ErpError) as e:
        submit(store, t, req, tok, key="k-2")
    assert e.value.code == "refused" and str(e.value) == "This request was already ordered."
    assert store.check_budget(t, "CT-OPS") == budget
    assert events(store, t, req["req_id"])[-1] == "refused"


def test_edit_voids_prior_approval(store, clock):
    t = "tenant-a"
    v1 = draft(store, t, "laptops", 12, "CT-OPS")
    tok_v1 = token_for(v1, t, clock)
    sku = v1["lines"][0]["sku"]
    q = store.get_price_quote(t, sku, 2)
    v2 = store.update_requisition(t, v1["req_id"], lines=[{"quote_id": q["quote_id"]}])
    assert v2["version"] == 2 and v2["content_hash"] != v1["content_hash"]
    assert v2["lines"][0]["quantity"] == 2
    assert events(store, t, v1["req_id"]) == ["created", "updated"]
    for version in (1, 2):
        with pytest.raises(ErpError) as e:
            store.submit_purchase_order(t, v1["req_id"], version, tok_v1, f"{v1['req_id']}:{version}")
        assert e.value.code == "refused" and "changed after approval" in str(e.value)
    v3 = store.update_requisition(t, v1["req_id"], justification="Smaller pilot")
    assert v3["version"] == 3 and v3["justification"] == "Smaller pilot"
    assert v3["content_hash"] != v2["content_hash"]
    assert submit(store, t, v3, token_for(v3, t, clock))["status"] == "ordered"
    with pytest.raises(ErpError) as e:
        store.update_requisition(t, v1["req_id"], justification="again")
    assert e.value.code == "invalid"


def test_tenant_isolation(store, clock):
    a, b = "tenant-a", "tenant-b"
    b_before = store.check_budget(b, "CT-OPS")
    req = draft(store, a, "laptops", 12, "CT-OPS")
    for call in (
        lambda: store.get_requisition(b, req["req_id"]),
        lambda: store.get_audit_trail(b, req["req_id"]),
        lambda: store.update_requisition(b, req["req_id"], justification="mine"),
        lambda: store.submit_purchase_order(b, req["req_id"], 1, token_for(req, b, clock), "k"),
    ):
        with pytest.raises(ErpError) as e:
            call()
        assert e.value.code == "not_found"
    submit(store, a, req, token_for(req, a, clock))
    assert store.check_budget(b, "CT-OPS") == b_before
    # B's own counters start fresh too.
    req_b = draft(store, b, "keyboards", 3, "CT-OPS")
    assert req_b["req_id"] == req["req_id"]
    assert submit(store, b, req_b, token_for(req_b, b, clock))["po_number"] == "PO-0001"


def test_ttl_purges_idle_tenant(db, clock):
    store = ErpStore(db, secret=SECRET, auto_limit_zar=LIMIT, tenant_ttl_hours=1, clock=clock)
    req = draft(store, "idle", "laptops", 12, "CT-OPS")
    submit(store, "idle", req, token_for(req, "idle", clock))
    fresh = store.check_budget("other", "CT-OPS")
    clock.advance(1800)
    store.check_budget("busy", "CT-OPS")
    assert store.get_requisition("idle", req["req_id"])["status"] == "ordered"  # touched: still alive
    clock.advance(3601)
    store.check_budget("busy", "CT-OPS")  # any call purges
    with pytest.raises(ErpError) as e:
        store.get_requisition("idle", req["req_id"])
    assert e.value.code == "not_found"
    assert store.check_budget("idle", "CT-OPS") == fresh  # back to fixture budgets
    store.close()


def test_record_approval_event(store, clock):
    t = "tenant-a"
    req = draft(store, t, "laptops", 12, "CT-OPS")
    store.record_approval_event(t, req["req_id"], 1, "approval_requested", "agent")
    store.record_approval_event(t, req["req_id"], 1, "rejected", "visitor:0123456789ab", reason="Too many")
    trail = store.get_audit_trail(t, req["req_id"])
    assert trail[-1]["event"] == "rejected" and trail[-1]["detail"] == "Too many"
    for bad in ("submitted", "refused", "created", "nope"):
        with pytest.raises(ErpError) as e:
            store.record_approval_event(t, req["req_id"], 1, bad, "x")
        assert e.value.code == "invalid"


def test_audit_trail_complete_and_ordered(store, clock):
    t = "tenant-a"
    req = draft(store, t, "laptops", 12, "CT-OPS")
    clock.advance(1)
    store.record_approval_event(t, req["req_id"], 1, "approval_requested", "agent")
    clock.advance(1)
    q = store.get_price_quote(t, req["lines"][0]["sku"], 11)
    v2 = store.update_requisition(t, req["req_id"], lines=[{"quote_id": q["quote_id"]}])
    clock.advance(1)
    with pytest.raises(ErpError):
        submit(store, t, v2, token_for(req, t, clock))
    store.record_approval_event(t, req["req_id"], 2, "approved", "visitor:0123456789ab")
    clock.advance(1)
    submit(store, t, v2, token_for(v2, t, clock))
    trail = store.get_audit_trail(t, req["req_id"])
    assert [e["event"] for e in trail] == [
        "created", "approval_requested", "updated", "refused", "approved", "submitted"]
    assert [e["version"] for e in trail] == [1, 1, 2, 2, 2, 2]
    assert all(set(e) == {"ts", "event", "version", "actor", "detail"} for e in trail)
    assert [e["ts"] for e in trail] == sorted(e["ts"] for e in trail)
    assert "PO-0001" in trail[-1]["detail"]


def test_auto_approved_event_accepted(store, clock):
    t = "tenant-a"
    req = draft(store, t, "keyboards", 3, "CT-OPS")
    store.record_approval_event(t, req["req_id"], 1, "auto_approved", "policy",
                                reason=policy.reason(req["total_zar"], LIMIT))
    assert events(store, t, req["req_id"]) == ["created", "auto_approved"]


def test_state_survives_reopen(db, clock, store):
    t = "tenant-a"
    req = draft(store, t, "laptops", 12, "CT-OPS")
    po = submit(store, t, req, token_for(req, t, clock))
    budget = store.check_budget(t, "CT-OPS")
    store.close()
    again = ErpStore(db, secret=SECRET, auto_limit_zar=LIMIT, tenant_ttl_hours=168, clock=clock)
    try:
        assert again.get_requisition(t, req["req_id"])["po_number"] == po["po_number"]
        assert again.check_budget(t, "CT-OPS") == budget
        assert events(again, t, req["req_id"]) == ["created", "submitted"]
        assert submit(again, t, req, token_for(req, t, clock)) == po
        nxt = draft(again, t, "keyboards", 3, "CT-OPS")
        assert nxt["req_id"] != req["req_id"]
    finally:
        again.close()


# ---------------------------------------------------------------- replay, races, studio events


def test_replay_same_key_after_token_expiry_returns_same_po(store, clock):
    t = "tenant-a"
    req = draft(store, t, "laptops", 12, "CT-OPS")
    tok = token_for(req, t, clock)
    po = submit(store, t, req, tok)
    trail = store.get_audit_trail(t, req["req_id"])
    clock.advance(901)  # token expired (and the quotes are still fine)
    assert submit(store, t, req, tok) == po
    clock.advance(1800)  # quotes expired too
    assert submit(store, t, req, tok) == po
    assert store.get_audit_trail(t, req["req_id"]) == trail


def test_replay_same_key_after_budget_spent_returns_same_po(store, clock):
    t = "tenant-a"
    req = draft(store, t, "laptops", 12, "CT-OPS")
    tok = token_for(req, t, clock)
    po = submit(store, t, req, tok)
    other = draft(store, t, "laptops", 6, "CT-OPS")
    submit(store, t, other, token_for(other, t, clock))
    assert store.check_budget(t, "CT-OPS")["remaining"] < req["total_zar"]
    budget = store.check_budget(t, "CT-OPS")
    trail = store.get_audit_trail(t, req["req_id"])
    assert submit(store, t, req, tok) == po
    assert store.check_budget(t, "CT-OPS") == budget
    assert store.get_audit_trail(t, req["req_id"]) == trail


def test_different_key_after_ordering_refused_even_with_bad_token(store, clock):
    t = "tenant-a"
    req = draft(store, t, "laptops", 12, "CT-OPS")
    submit(store, t, req, token_for(req, t, clock))
    for tok in ("not-a-token", token_for(req, t, clock, secret=b"other")):
        with pytest.raises(ErpError) as e:
            submit(store, t, req, tok, key="another-key")
        assert e.value.code == "refused" and str(e.value) == "This request was already ordered."
        assert store.get_audit_trail(t, req["req_id"])[-1]["detail"] == "This request was already ordered."


@pytest.mark.parametrize("shared", [True, False], ids=["one store", "two stores on one file"])
def test_concurrent_submits_place_one_po(db, clock, shared):
    import threading

    stores = [ErpStore(db, secret=SECRET, auto_limit_zar=LIMIT, tenant_ttl_hours=168, clock=clock)]
    stores.append(stores[0] if shared else
                  ErpStore(db, secret=SECRET, auto_limit_zar=LIMIT, tenant_ttl_hours=168, clock=clock))
    t = "tenant-a"
    before = stores[0].check_budget(t, "CT-OPS")
    req = draft(stores[0], t, "laptops", 12, "CT-OPS")
    tok = token_for(req, t, clock)
    barrier = threading.Barrier(2)
    results = []

    def go(i):
        barrier.wait()
        try:
            results.append(submit(stores[i], t, req, tok, key=f"key-{i}"))
        except ErpError as err:
            results.append(err)

    threads = [threading.Thread(target=go, args=(i,)) for i in range(2)]
    for th in threads:
        th.start()
    for th in threads:
        th.join(10)
    pos = [r for r in results if isinstance(r, dict)]
    errs = [r for r in results if isinstance(r, ErpError)]
    assert len(pos) == 1 and len(errs) == 1
    assert str(errs[0]) == "This request was already ordered."
    after = stores[0].check_budget(t, "CT-OPS")
    assert after["committed"] == before["committed"] + req["total_zar"]
    assert events(stores[0], t, req["req_id"]).count("submitted") == 1
    for s in {id(s): s for s in stores}.values():
        s.close()


def test_record_approval_event_rejects_unknown_version_and_ordered(store, clock):
    t = "tenant-a"
    req = draft(store, t, "laptops", 12, "CT-OPS")
    for bad in (0, 2, True, "1"):
        with pytest.raises(ErpError) as e:
            store.record_approval_event(t, req["req_id"], bad, "approved", "visitor:0123456789ab")
        assert e.value.code == "invalid", bad
    submit(store, t, req, token_for(req, t, clock))
    trail = store.get_audit_trail(t, req["req_id"])
    with pytest.raises(ErpError) as e:
        store.record_approval_event(t, req["req_id"], 1, "rejected", "visitor:0123456789ab")
    assert e.value.code == "invalid"
    assert store.get_audit_trail(t, req["req_id"]) == trail
