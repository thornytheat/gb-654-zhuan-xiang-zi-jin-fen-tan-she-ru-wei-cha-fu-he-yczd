import csv
import io
from decimal import Decimal

from app import rulebook
from app.manifest import canonical_digest, run_id


def _sample_weight_set() -> dict:
    from app.modules.m3_weights.core import build as build_weights

    decisions = [
        {"id": "A", "eligible": True, "reason": "RURAL",
         "rule_version": rulebook.CURRENT_RULE_VERSION},
        {"id": "B", "eligible": True, "reason": "DEFAULT",
         "rule_version": rulebook.CURRENT_RULE_VERSION},
        {"id": "C", "eligible": True, "reason": "DEFAULT",
         "rule_version": rulebook.CURRENT_RULE_VERSION},
    ]
    items = [{"id": "A", "weight": "5"}, {"id": "B", "weight": "3"}, {"id": "C", "weight": "2"}]
    return build_weights({"decisions": decisions, "items": items})["weight_set"]


SAMPLE = {
    "store": None,
    "batch_id": "BATCH-0001",
    "version": 2,
    "expected_version": 2,
    "rows": [
        {"project_id": "A", "amount": "300.00", "reason": "CAP"},
        {"project_id": "B", "amount": "420.00", "reason": "WEIGHT"},
        {"project_id": "C", "amount": "280.00", "reason": "WEIGHT"},
    ],
    "approved": "1000.00",
    "decisions": [
        {"id": "A", "eligible": True, "reason": "RURAL",
         "rule_version": rulebook.CURRENT_RULE_VERSION},
        {"id": "B", "eligible": True, "reason": "DEFAULT",
         "rule_version": rulebook.CURRENT_RULE_VERSION},
        {"id": "C", "eligible": True, "reason": "DEFAULT",
         "rule_version": rulebook.CURRENT_RULE_VERSION},
    ],
    "weight_set": _sample_weight_set(),
}


def csv_text(rows):
    out = io.StringIO()
    writer = csv.DictWriter(
        out, fieldnames=["project_id", "amount", "reason"], lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def batch_key(payload: dict, rows) -> str:
    """批次业务键：有 batch_id 用批次号，否则退回行内容摘要。"""
    batch_id = payload.get("batch_id")
    if batch_id:
        return canonical_digest({"batch_id": str(batch_id)})
    return canonical_digest({"rows": rows})


def eligibility_basis(decisions):
    return [
        {
            "id": str(item["id"]),
            "eligible": bool(item["eligible"]),
            "reason": item.get("reason"),
            "rule_version": item.get("rule_version"),
        }
        for item in sorted(decisions, key=lambda item: str(item["id"]))
    ]


def build_snapshot(payload: dict, rows, total: Decimal, approved: Decimal) -> dict:
    """固化签批当天的资格与权重依据，供日后按当日依据复核。"""
    decisions = payload.get("decisions") or []
    weight_set = payload.get("weight_set") or {}
    rule_version = str(payload.get("rule_version") or weight_set.get("rule_version") or "")

    if weight_set:
        set_version = str(weight_set.get("rule_version") or "")
        if rule_version and set_version and rule_version != set_version:
            raise ValueError("RULEBOOK_MISMATCH")
        rule_version = rule_version or set_version
    else:
        rule_version = rule_version or rulebook.current_version()
    if not rulebook.is_known(rule_version):
        raise ValueError("UNKNOWN_RULE_VERSION")

    basis_digest = weight_set.get("basis_digest")
    if decisions:
        computed = rulebook.basis_digest(decisions)
        if basis_digest and basis_digest != computed:
            raise ValueError("RULEBOOK_MISMATCH")
        basis_digest = basis_digest or computed
        mismatched = [
            item for item in decisions
            if item.get("rule_version") and str(item["rule_version"]) != rule_version
        ]
        if mismatched:
            raise ValueError("RULEBOOK_MISMATCH")

    return {
        "batch_id": payload.get("batch_id"),
        "rule_version": rule_version,
        "rulebook_digest": weight_set.get("rulebook_digest")
        or rulebook.rulebook_digest(rule_version),
        "weight_set_digest": weight_set.get("weight_set_digest"),
        "eligibility": eligibility_basis(decisions),
        "weights": [
            {"id": str(x["id"]), "weight": str(x["weight"]), "share": str(x.get("share", ""))}
            for x in (weight_set.get("entries") or [])
        ],
        "rows": rows,
        "allocated_total": str(total),
        "approved": str(approved),
        "balanced": total == approved,
    }


def snapshot_digest(snapshot: dict) -> str:
    return canonical_digest(snapshot)


def require_signable(payload: dict) -> None:
    """签批必须带齐证据：批次行、当日资格判定与当前规则测算的权重。"""
    if not payload.get("rows"):
        raise ValueError("EMPTY_VALUE")
    if not payload.get("decisions"):
        raise ValueError("MISSING_DECISIONS")
    weight_set = payload.get("weight_set") or {}
    if not weight_set:
        raise ValueError("MISSING_WEIGHT_SET")
    if not rulebook.weight_set_is_current(weight_set):
        raise ValueError("STALE_WEIGHT")


def sign(store, payload: dict) -> dict:
    """签批留档。

    同一批次重试签批只留首次档：返回原 run_id，不新增记录。
    已签批次不因规则更新而改写，复核时按快照中的当日依据。
    签批不套用样例数据，必须显式给出批次内容与依据。
    """
    if store is None:
        raise ValueError("MISSING_STORE")
    d = dict(payload or {})
    if not d:
        raise ValueError("EMPTY_VALUE")
    d.setdefault("version", 1)
    d.setdefault("expected_version", d["version"])
    if int(d["version"]) != int(d["expected_version"]):
        raise ValueError("STALE_VERSION")

    rows = d.get("rows") or []
    total = sum((Decimal(str(x["amount"])) for x in rows), Decimal(0))
    approved = Decimal(str(d.get("approved", total)))
    key = batch_key(d, rows)
    snapshot = build_snapshot(d, rows, total, approved)
    digest = snapshot_digest(snapshot)

    existing = store.approval(key) if hasattr(store, "approval") else None
    if existing is not None:
        archived = existing["snapshot"]
        if snapshot_digest(archived) != digest:
            raise ValueError("DUPLICATE_APPROVAL")
        return {
            "status": "READY",
            "run_id": existing["run_id"],
            "batch_key": key,
            "snapshot_digest": snapshot_digest(archived),
            "reused": True,
            "snapshot": archived,
            "reason": "SIGNED",
        }

    require_signable(d)
    rid = run_id(key)
    if hasattr(store, "record_approval"):
        saved = store.record_approval(key, rid, snapshot)
        return {
            "status": "READY",
            "run_id": saved["run_id"],
            "batch_key": key,
            "snapshot_digest": snapshot_digest(saved["snapshot"]),
            "reused": saved["run_id"] != rid,
            "snapshot": saved["snapshot"],
            "reason": "SIGNED",
        }
    saved = store.record(key, rid, snapshot)
    return {
        "status": "READY",
        "run_id": saved["run_id"],
        "batch_key": key,
        "snapshot_digest": snapshot_digest(snapshot),
        "reused": False,
        "snapshot": snapshot,
        "reason": "SIGNED",
    }


def recheck(store, key: str) -> dict:
    """按签批当天快照复核已签批次，不受后续规则更新影响。"""
    if store is None or not hasattr(store, "approval"):
        raise ValueError("MISSING_STORE")
    existing = store.approval(key)
    if existing is None:
        raise ValueError("NOT_FOUND")
    snapshot = existing["snapshot"]
    return {
        "status": "READY",
        "run_id": existing["run_id"],
        "batch_key": key,
        "snapshot_digest": snapshot_digest(snapshot),
        "rule_version": snapshot["rule_version"],
        "eligibility": snapshot["eligibility"],
        "weights": snapshot["weights"],
        "snapshot": snapshot,
        "reason": "OK",
    }


def run(payload):
    """批次复核视图：汇总输入、有效、隔离与输出合计，并展示签批快照。"""
    d = dict(SAMPLE)
    d.update(payload or {})
    if int(d["version"]) != int(d["expected_version"]):
        raise ValueError("STALE_VERSION")

    rows = d["rows"]
    total = sum((Decimal(str(x["amount"])) for x in rows), Decimal(0))
    approved = Decimal(str(d["approved"]))
    digest = canonical_digest(rows)
    snapshot = build_snapshot(d, rows, total, approved)
    key = batch_key(d, rows)
    rid = run_id(digest)
    result = {
        "input_count": len(rows),
        "valid_count": len(rows),
        "quarantine_count": 0,
        "allocated_total": str(total),
        "approved": str(approved),
        "balanced": total == approved,
    }
    store = d.get("store")
    if store:
        rid = store.record(digest, rid, result)["run_id"]
    return {
        "status": "READY",
        "run_id": rid,
        "digest": digest,
        "batch_key": key,
        "csv": csv_text(rows),
        **result,
        "rule_version": snapshot["rule_version"],
        "eligibility": snapshot["eligibility"],
        "weights": snapshot["weights"],
        "reason": "OK" if total == approved else "DIFF",
    }
