from decimal import Decimal

from app import rulebook

SAMPLE = {
    "total": "1000.00",
    "items": [
        {"id": "A", "weight": "5", "cap": "300.00"},
        {"id": "B", "weight": "3", "cap": "500.00"},
        {"id": "C", "weight": "2", "cap": "500.00"},
    ],
}


def allocate(total, items):
    remaining = Decimal(str(total))
    pending = {
        str(x["id"]): {"weight": Decimal(str(x["weight"])), "cap": Decimal(str(x["cap"]))}
        for x in items
    }
    out = {k: Decimal(0) for k in pending}
    while pending and remaining > 0:
        total_weight = sum((x["weight"] for x in pending.values()), Decimal(0))
        if total_weight <= 0:
            break
        capped = []
        for key, item in pending.items():
            proposal = remaining * item["weight"] / total_weight
            room = item["cap"] - out[key]
            if proposal >= room:
                out[key] += room
                capped.append(key)
        if not capped:
            for key, item in pending.items():
                out[key] += remaining * item["weight"] / total_weight
            remaining = Decimal(0)
            break
        remaining = Decimal(str(total)) - sum(out.values())
        for key in capped:
            pending.pop(key)
    return out, remaining


def items_from_weight_set(weight_set: dict, caps: dict) -> list[dict]:
    entries = weight_set.get("entries") or []
    if not entries:
        raise ValueError("EMPTY_WEIGHT_SET")
    items = []
    for entry in entries:
        key = str(entry["id"])
        if key not in caps:
            raise ValueError("MISSING_CAP")
        items.append({"id": key, "weight": entry["weight"], "cap": caps[key]})
    return items


def require_current(weight_set: dict) -> str:
    """未签批次只能使用当前资格规则重新测算的权重。

    规则更新后旧权重一律失效，即使项目已从名单中剔除，
    也不能沿用带旧权重的分摊结果。
    """
    if not weight_set:
        raise ValueError("MISSING_WEIGHT_SET")
    if not rulebook.weight_set_is_current(weight_set):
        raise ValueError("STALE_WEIGHT")
    return str(weight_set.get("rule_version"))


def require_eligible(items, decisions, weight_set=None) -> None:
    """被剔除的项目不得再参与分摊，即使调用方直接传了它的权重。

    权重集里固化的资格依据必须与本次提交的判定一致，
    不能拿新判定去套旧权重。
    """
    if not decisions:
        return
    if weight_set and weight_set.get("basis_digest"):
        if rulebook.basis_digest(decisions) != weight_set["basis_digest"]:
            raise ValueError("RULEBOOK_MISMATCH")
    allowed = rulebook.eligible_ids(decisions)
    blocked = sorted(str(x["id"]) for x in items if str(x["id"]) not in allowed)
    if blocked:
        raise ValueError("NOT_ELIGIBLE_PROJECT")


def run(payload):
    payload = payload or {}
    caps = payload.get("caps")
    if payload.get("weight_set"):
        weight_set = payload["weight_set"]
        version = require_current(weight_set)
        caps = caps or {}
        items = items_from_weight_set(weight_set, caps)
        total = payload.get("total", SAMPLE["total"])
    else:
        weight_set = None
        claimed = payload.get("rule_version")
        version = str(claimed or rulebook.current_version())
        if claimed and version != rulebook.current_version():
            # 没有权重集的直传项目也不得声称按旧规则分摊
            raise ValueError("STALE_WEIGHT")
        items = payload.get("items", SAMPLE["items"])
        total = payload.get("total", SAMPLE["total"])
    require_eligible(items, payload.get("decisions"), weight_set)
    out, left = allocate(total, items)
    return {
        "status": "READY",
        "rule_version": version,
        "weight_set_digest": (payload.get("weight_set") or {}).get("weight_set_digest"),
        "input_count": len(out),
        "valid_count": len(out),
        "quarantine_count": 0,
        "allocated": {k: str(v) for k, v in out.items()},
        "allocated_total": str(sum(out.values())),
        "unallocated": str(left),
        "reason": "OK" if left == 0 else "CAP_LIMIT",
    }
