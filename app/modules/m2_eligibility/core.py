from app import rulebook

SAMPLE = {
    "projects": [
        {"id": "A", "region": "rural", "score": 82, "blacklisted": False},
        {"id": "B", "region": "urban", "score": 95, "blacklisted": True},
        {"id": "C", "region": "rural", "score": 55, "blacklisted": False},
    ],
    "excluded_project_ids": [],
}


def _with_version(rules, version):
    return [dict(rule, version=version) for rule in rules]


# 历史规则（2026.11）原样保留，供已签批次按签批当日依据复核。
RULES = _with_version(rulebook.RULEBOOKS[rulebook.PREVIOUS_RULE_VERSION],
                      rulebook.PREVIOUS_RULE_VERSION)

# 2026.12 起先按剔除名单判一次，再走原有规则。
RULES_2026_12 = _with_version(rulebook.RULEBOOKS[rulebook.CURRENT_RULE_VERSION],
                              rulebook.CURRENT_RULE_VERSION)


def rules_for(version: str):
    if version == rulebook.PREVIOUS_RULE_VERSION:
        return RULES
    if version == rulebook.CURRENT_RULE_VERSION:
        return RULES_2026_12
    raise ValueError("UNKNOWN_RULE_VERSION")


def evaluate(project, rules=None, excluded=None, version=None):
    """按指定规则版本判定资格。

    同一优先级出现互斥结论时报 RULE_CONFLICT，交复核处理，
    而不是让输入顺序决定结果。
    """
    version = str(version or rulebook.PREVIOUS_RULE_VERSION)
    rules = rules if rules is not None else rules_for(version)
    excluded = {str(x) for x in (excluded or [])}
    hits = [
        (rule["priority"], rule["code"], rule["eligible"])
        for rule in rules
        if rulebook.matches(rule, project, excluded)
    ]
    if not hits:
        raise ValueError("NO_RULE_MATCHED")
    best = max(hit[0] for hit in hits)
    top = [hit for hit in hits if hit[0] == best]
    if len({hit[2] for hit in top}) > 1:
        raise ValueError("RULE_CONFLICT")
    priority, code, allowed = top[0]
    return {
        "id": str(project["id"]),
        "eligible": allowed,
        "reason": code,
        "priority": priority,
        "rule_version": version,
    }


def run(payload):
    payload = payload or {}
    version = str(payload.get("rule_version") or rulebook.current_version())
    rules_for(version)
    projects = payload.get("projects", SAMPLE["projects"])
    excluded = payload.get("excluded_project_ids", SAMPLE["excluded_project_ids"])
    out = [evaluate(x, None, excluded, version) for x in projects]
    return {
        "status": "READY",
        "rule_version": version,
        "rulebook_digest": rulebook.rulebook_digest(version),
        "basis_digest": rulebook.basis_digest(out),
        "input_count": len(out),
        "valid_count": sum(x["eligible"] for x in out),
        "quarantine_count": sum(not x["eligible"] for x in out),
        "decisions": out,
        "reason": "REVIEW",
    }
