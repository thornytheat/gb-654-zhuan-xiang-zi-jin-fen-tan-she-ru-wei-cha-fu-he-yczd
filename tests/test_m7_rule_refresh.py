"""资格规则更新后，旧权重失效、签批依据可复核的回归测试。"""

from decimal import Decimal

import pytest

from app import rulebook
from app.modules.m2_eligibility.core import run as eligibility_run
from app.modules.m3_weights.core import build, is_current
from app.modules.m4_allocations.core import run as allocation_run
from app.modules.m6_runs import core as runs_core
from app.store import Store

PROJECTS = [
    {"id": "X", "region": "urban", "score": 90, "blacklisted": False},
    {"id": "Y", "region": "rural", "score": 90, "blacklisted": False},
]
ITEMS = [{"id": "X", "weight": 1}, {"id": "Y", "weight": 1}]


def decisions(version, excluded=("X",)):
    return eligibility_run(
        {"projects": PROJECTS, "excluded_project_ids": list(excluded), "rule_version": version}
    )


def test_removed_project_passes_old_rule_fails_new_rule():
    old = {d["id"]: d for d in decisions(rulebook.PREVIOUS_RULE_VERSION)["decisions"]}
    new = {d["id"]: d for d in decisions(rulebook.CURRENT_RULE_VERSION)["decisions"]}
    assert old["X"]["eligible"] is True and old["X"]["reason"] == "DEFAULT"
    assert new["X"]["eligible"] is False and new["X"]["reason"] == "EXCLUDED_PROJECT"
    assert new["Y"]["eligible"] is True


def test_old_weight_set_is_stale_new_one_is_current():
    old_rules = decisions(rulebook.PREVIOUS_RULE_VERSION)
    old_weight = build(
        {"rule_version": rulebook.PREVIOUS_RULE_VERSION, "decisions": old_rules["decisions"],
         "items": ITEMS}
    )["weight_set"]
    new_rules = decisions(rulebook.CURRENT_RULE_VERSION)
    new_weight = build({"decisions": new_rules["decisions"], "items": ITEMS})["weight_set"]

    assert {entry["id"] for entry in old_weight["entries"]} == {"X", "Y"}
    assert is_current(old_weight) is False
    assert is_current(new_weight) is True
    assert [e["id"] for e in new_weight["entries"]] == ["Y"]
    assert old_weight["weight_set_digest"] != new_weight["weight_set_digest"]


def test_allocation_rejects_stale_weight_set():
    old_rules = decisions(rulebook.PREVIOUS_RULE_VERSION)
    old_weight = build(
        {"rule_version": rulebook.PREVIOUS_RULE_VERSION, "decisions": old_rules["decisions"],
         "items": ITEMS}
    )["weight_set"]
    with pytest.raises(ValueError) as exc:
        allocation_run({"total": "100", "weight_set": old_weight,
                        "caps": {"X": "100", "Y": "100"}})
    assert str(exc.value) == "STALE_WEIGHT"


def test_allocation_uses_recalculated_weight_only():
    new_rules = decisions(rulebook.CURRENT_RULE_VERSION)
    new_weight = build({"decisions": new_rules["decisions"], "items": ITEMS})["weight_set"]
    out = allocation_run({"total": "100", "weight_set": new_weight, "caps": {"Y": "100"}})
    assert out["allocated"] == {"Y": "100"}
    assert "X" not in out["allocated"]


def test_removed_project_gets_no_money_even_if_items_passed_directly():
    new_rules = decisions(rulebook.CURRENT_RULE_VERSION)
    items = [{"id": "X", "weight": 1, "cap": "100"}, {"id": "Y", "weight": 1, "cap": "100"}]
    with pytest.raises(ValueError) as exc:
        allocation_run({"total": "100", "items": items, "decisions": new_rules["decisions"]})
    assert str(exc.value) == "NOT_ELIGIBLE_PROJECT"


def test_api_flow_excludes_removed_project_from_allocation(client):
    projects = [dict(p) for p in PROJECTS]
    items = [dict(i) for i in ITEMS]
    evaluated = client.post(
        "/api/eligibility/evaluate",
        json={"projects": projects, "excluded_project_ids": ["X"]},
    ).json()
    assert evaluated["rule_version"] == rulebook.CURRENT_RULE_VERSION

    weighted = client.post(
        "/api/weights/calculate",
        json={"decisions": evaluated["decisions"], "items": items},
    ).json()
    assert [entry["id"] for entry in weighted["weight_set"]["entries"]] == ["Y"]

    allocated = client.post(
        "/api/allocations/calculate",
        json={"total": "100.00", "weight_set": weighted["weight_set"],
              "caps": {"Y": "100.00"}},
    ).json()
    assert allocated["allocated"] == {"Y": "100.00"}
    assert allocated["rule_version"] == rulebook.CURRENT_RULE_VERSION

    # 旧规则权重不能再用于新的未签批次
    stale = client.post(
        "/api/allocations/calculate",
        json={"total": "100.00",
              "weight_set": _signed_payload(
                  rulebook.PREVIOUS_RULE_VERSION, "BATCH-OLD-WEIGHT")["weight_set"],
              "caps": {"X": "100.00", "Y": "100.00"}},
    )
    assert stale.status_code == 422
    assert stale.json()["error"] == "STALE_WEIGHT"


def test_allocation_rejects_decisions_that_straddle_basis():
    new_rules = decisions(rulebook.CURRENT_RULE_VERSION)
    new_weight = build({"decisions": new_rules["decisions"], "items": ITEMS})["weight_set"]
    old_rules = decisions(rulebook.PREVIOUS_RULE_VERSION)
    with pytest.raises(ValueError) as exc:
        allocation_run({"total": "100", "weight_set": new_weight,
                        "decisions": old_rules["decisions"],
                        "caps": {"Y": "100"}})
    assert str(exc.value) == "RULEBOOK_MISMATCH"


def test_weight_digest_changes_when_rulebook_changes():
    old = decisions(rulebook.PREVIOUS_RULE_VERSION)
    old_weight = build(
        {"rule_version": rulebook.PREVIOUS_RULE_VERSION, "decisions": old["decisions"],
         "items": ITEMS}
    )["weight_set"]
    # 手工把同一份权重标成新版本也不行：规则清单摘要与依据摘要都必须匹配
    forged = dict(old_weight, rule_version=rulebook.CURRENT_RULE_VERSION)
    with pytest.raises(ValueError):
        allocation_run({"total": "100", "weight_set": forged,
                        "caps": {"X": "100", "Y": "100"}})


def test_tampered_weight_entries_are_stale():
    new_rules = decisions(rulebook.CURRENT_RULE_VERSION)
    weight = build({"decisions": new_rules["decisions"], "items": ITEMS})["weight_set"]
    tampered = dict(weight, entries=[{"id": "Y", "weight": "1", "share": "1"},
                                     {"id": "X", "weight": "1", "share": "1"}])
    assert is_current(tampered) is False
    with pytest.raises(ValueError):
        allocation_run({"total": "100", "weight_set": tampered,
                        "caps": {"X": "100", "Y": "100"}})


def test_weight_build_rejects_decisions_from_other_rule_version():
    old = decisions(rulebook.PREVIOUS_RULE_VERSION)
    with pytest.raises(ValueError) as exc:
        build({"rule_version": rulebook.CURRENT_RULE_VERSION,
               "decisions": old["decisions"], "items": ITEMS})
    assert str(exc.value) == "RULEBOOK_MISMATCH"


def _signed_payload(version, batch_id):
    decided = decisions(version)
    weight = build(
        {"rule_version": version, "decisions": decided["decisions"], "items": ITEMS}
    )["weight_set"]
    rows = [
        {"project_id": entry["id"], "amount": "50.00", "reason": "WEIGHT"}
        for entry in weight["entries"]
    ]
    approved = str(sum(Decimal(row["amount"]) for row in rows))
    return {
        "batch_id": batch_id,
        "rows": rows,
        "approved": approved,
        "decisions": decided["decisions"],
        "weight_set": weight,
        "version": 2,
        "expected_version": 2,
    }


def test_approval_snapshot_keeps_signing_day_basis(tmp_path):
    store = Store(str(tmp_path / "a.db"))
    old = _signed_payload(rulebook.PREVIOUS_RULE_VERSION, "BATCH-OLD")
    # 模拟规则更新前已签批：当时快照里的 X 仍然有效
    snapshot = runs_core.build_snapshot(
        old, old["rows"], 100, 100
    )
    store.record_approval(runs_core.batch_key(old, old["rows"]), "run-old", snapshot)

    reread = runs_core.recheck(store, runs_core.batch_key(old, old["rows"]))
    assert reread["rule_version"] == rulebook.PREVIOUS_RULE_VERSION
    assert {row["id"]: row["eligible"] for row in reread["eligibility"]} == {"X": True, "Y": True}
    assert [w["id"] for w in reread["weights"]] == ["X", "Y"]


def test_unsigned_batch_cannot_sign_with_stale_weight(tmp_path):
    store = Store(str(tmp_path / "b.db"))
    payload = _signed_payload(rulebook.PREVIOUS_RULE_VERSION, "BATCH-STALE")
    with pytest.raises(ValueError) as exc:
        runs_core.sign(store, payload)
    assert str(exc.value) == "STALE_WEIGHT"


def test_approval_retry_does_not_duplicate_archive(tmp_path):
    store = Store(str(tmp_path / "c.db"))
    payload = _signed_payload(rulebook.CURRENT_RULE_VERSION, "BATCH-NEW")
    first = runs_core.sign(store, payload)
    second = runs_core.sign(store, payload)
    assert first["run_id"] == second["run_id"]
    assert second["reused"] is True
    assert store.approval_count() == 1


def test_approval_snapshot_contains_eligibility_and_weights(tmp_path):
    store = Store(str(tmp_path / "d.db"))
    payload = _signed_payload(rulebook.CURRENT_RULE_VERSION, "BATCH-EVIDENCE")
    saved = runs_core.sign(store, payload)
    snapshot = saved["snapshot"]
    assert snapshot["rule_version"] == rulebook.CURRENT_RULE_VERSION
    assert snapshot["rulebook_digest"] == rulebook.rulebook_digest(
        rulebook.CURRENT_RULE_VERSION
    )
    assert snapshot["eligibility"] == [
        {"id": "X", "eligible": False, "reason": "EXCLUDED_PROJECT",
         "rule_version": rulebook.CURRENT_RULE_VERSION},
        {"id": "Y", "eligible": True, "reason": "RURAL",
         "rule_version": rulebook.CURRENT_RULE_VERSION},
    ]
    assert snapshot["weights"] == [{"id": "Y", "weight": "1", "share": "1"}]
    assert snapshot["rule_version"] == rulebook.CURRENT_RULE_VERSION


def test_retry_of_legacy_signed_batch_still_replays(tmp_path):
    """已签批的旧规则批次重试签批：复用原档，不报过期、不重复留档。"""
    store = Store(str(tmp_path / "f.db"))
    payload = _signed_payload(rulebook.PREVIOUS_RULE_VERSION, "BATCH-LEGACY")
    snapshot = runs_core.build_snapshot(
        payload, payload["rows"], Decimal(payload["approved"]), Decimal(payload["approved"])
    )
    store.record_approval(
        runs_core.batch_key(payload, payload["rows"]), "run-legacy", snapshot
    )

    replay = runs_core.sign(store, payload)
    assert replay["run_id"] == "run-legacy"
    assert replay["reused"] is True
    assert replay["snapshot"]["rule_version"] == rulebook.PREVIOUS_RULE_VERSION
    assert store.approval_count() == 1


def test_conflicting_resign_is_rejected(tmp_path):
    store = Store(str(tmp_path / "e.db"))
    payload = _signed_payload(rulebook.CURRENT_RULE_VERSION, "BATCH-CONFLICT")
    runs_core.sign(store, payload)
    changed = dict(payload, approved="99.00")
    with pytest.raises(ValueError) as exc:
        runs_core.sign(store, changed)
    assert str(exc.value) == "DUPLICATE_APPROVAL"


def test_api_approval_retry_and_recheck(client):
    payload = _signed_payload(rulebook.CURRENT_RULE_VERSION, "BATCH-API")
    first = client.post("/api/runs/approve", json=payload)
    second = client.post("/api/runs/approve", json=payload)
    assert first.status_code == second.status_code == 200
    assert first.json()["run_id"] == second.json()["run_id"]
    assert second.json()["reused"] is True

    listed = client.get("/api/runs").json()
    assert len(listed["approvals"]) == 1
    archived = listed["approvals"][0]["snapshot"]
    assert archived["eligibility"][0]["id"] == "X"
    assert archived["weights"] == [{"id": "Y", "weight": "1", "share": "1"}]

    rerun = client.get(f"/api/runs/{first.json()['batch_key']}/recheck")
    assert rerun.status_code == 200
    assert rerun.json()["snapshot"] == archived


def test_api_rejects_stale_weight(client):
    payload = _signed_payload(rulebook.PREVIOUS_RULE_VERSION, "BATCH-API-STALE")
    response = client.post("/api/runs/approve", json=payload)
    assert response.status_code == 422
    assert response.json()["error"] == "STALE_WEIGHT"


def test_runs_page_shows_signed_basis(client):
    payload = _signed_payload(rulebook.CURRENT_RULE_VERSION, "BATCH-PAGE")
    client.post("/api/runs/approve", json=payload)
    page = client.get("/runs")
    assert page.status_code == 200
    assert "签批依据快照" in page.text
    assert "已签批留档" in page.text
    assert "Y=1" in page.text
    assert "X:剔除(EXCLUDED_PROJECT)" in page.text

