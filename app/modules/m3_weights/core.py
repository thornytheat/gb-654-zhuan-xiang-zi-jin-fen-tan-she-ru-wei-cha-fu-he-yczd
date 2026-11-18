from decimal import Decimal

from app import rulebook as rules_registry

SAMPLE = {
    "items": [{"id": "A", "weight": "2"}, {"id": "B", "weight": "1"}, {"id": "C", "weight": "0"}],
}


def normalize(items):
    weights = [Decimal(str(x["weight"])) for x in items]
    if any(x < 0 for x in weights):
        raise ValueError("NEGATIVE_WEIGHT")
    total = sum(weights, Decimal(0))
    if total == 0:
        raise ValueError("ZERO_WEIGHT_GROUP")
    return [
        {"id": str(item["id"]), "weight": weight, "share": weight / total}
        for item, weight in zip(items, weights)
    ]


def weight_set_digest(rule_version: str, basis_digest, entries) -> str:
    return rules_registry.weight_set_digest(rule_version, basis_digest, entries)


def decisions_for(payload: dict, rule_version: str):
    """有 projects 时按规则版本现算资格；否则直接采信调用方传入的判定。

    传入判定必须声明本次测算的规则版本，避免把旧规则结论
    包装成新规则下的权重。
    """
    if "decisions" in payload:
        decisions = payload["decisions"]
        for item in decisions:
            declared = item.get("rule_version")
            if not declared or str(declared) != rule_version:
                raise ValueError("RULEBOOK_MISMATCH")
        return decisions
    if "projects" in payload:
        from app.modules.m2_eligibility.core import evaluate

        excluded = payload.get("excluded_project_ids", [])
        return [
            evaluate(project, None, excluded, rule_version)
            for project in payload["projects"]
        ]
    return None


def build(payload):
    """按资格依据测算权重。

    权重集绑定测算时的规则版本、规则清单摘要和资格依据摘要：
    - 资格规则更新后，旧版本测算的权重集不再被未签批次采信；
    - 已签批次仍可按当时留档的权重集复核。
    """
    payload = payload or {}
    rule_version = str(payload.get("rule_version") or rules_registry.current_version())
    rules_registry.rules_for(rule_version)

    decisions = decisions_for(payload, rule_version)
    excluded = []
    if decisions is None:
        basis_digest = None
        items = payload.get("items", SAMPLE["items"])
    else:
        basis_digest = rules_registry.basis_digest(decisions)
        allowed = rules_registry.eligible_ids(decisions)
        source = payload.get("items")
        if source is None:
            source = [{"id": item_id, "weight": 1} for item_id in sorted(allowed)]
        items = [x for x in source if str(x["id"]) in allowed]
        excluded = [
            {"id": str(x["id"]), "reason": x.get("reason"), "rule_version": x.get("rule_version")}
            for x in decisions
            if not x["eligible"]
        ]

    entries = normalize(items)
    book_digest = rules_registry.rulebook_digest(rule_version)
    digest = weight_set_digest(rule_version, basis_digest, entries)
    return {
        "status": "READY",
        "rule_version": rule_version,
        "rulebook_digest": book_digest,
        "basis_digest": basis_digest,
        "weight_set_digest": digest,
        "input_count": len(entries) + len(excluded),
        "valid_count": len(entries),
        "quarantine_count": len(excluded),
        "share_sum": str(sum((x["share"] for x in entries), Decimal(0)).normalize()),
        "shares": {x["id"]: str(x["share"]) for x in entries},
        "weights": {x["id"]: str(x["weight"]) for x in entries},
        "excluded": excluded,
        "weight_set": {
            "rule_version": rule_version,
            "rulebook_digest": book_digest,
            "basis_digest": basis_digest,
            "weight_set_digest": digest,
            "entries": [
                {"id": x["id"], "weight": str(x["weight"]), "share": str(x["share"])}
                for x in entries
            ],
        },
        "reason": "OK",
    }


def is_current(weight_set: dict) -> bool:
    """旧规则的权重集一律失效，须按当前规则重新测算才能用于未签批次。"""
    return rules_registry.weight_set_is_current(weight_set)


def run(payload):
    out = build(payload)
    out["usable_for_unsigned"] = is_current(out["weight_set"])
    return out
