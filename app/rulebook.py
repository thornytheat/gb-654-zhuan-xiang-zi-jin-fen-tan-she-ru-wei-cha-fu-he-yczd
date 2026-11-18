"""资格规则登记。

规则一经签批即固定：历史版本保留，供已签批次按签批当日依据复核；
规则更新后，按旧版本测算的权重集不再适用于未签批次，必须重新测算。
"""

from app.manifest import canonical_digest

PREVIOUS_RULE_VERSION = "2026.11"
CURRENT_RULE_VERSION = "2026.12"
KNOWN_RULE_VERSIONS = (PREVIOUS_RULE_VERSION, CURRENT_RULE_VERSION)

# 2026.11：仅按黑名单、评分和区域判定。
_BASE_RULES = (
    {"code": "BLACKLIST", "priority": 100, "eligible": False,
     "when": "blacklisted is true"},
    {"code": "LOW_SCORE", "priority": 80, "eligible": False,
     "when": "score < 60"},
    {"code": "RURAL", "priority": 20, "eligible": True,
     "when": "region == rural"},
    {"code": "DEFAULT", "priority": 0, "eligible": True,
     "when": "otherwise"},
)

# 2026.12：新增剔除名单，优先于黑名单先行剔除。
_EXCLUSION_RULE = {
    "code": "EXCLUDED_PROJECT",
    "priority": 110,
    "eligible": False,
    "when": "project_id in excluded_project_ids",
}

RULEBOOKS = {
    PREVIOUS_RULE_VERSION: _BASE_RULES,
    CURRENT_RULE_VERSION: (_EXCLUSION_RULE,) + _BASE_RULES,
}


def current_version() -> str:
    """当前生效的资格规则版本。

    以代码登记为准，不随部署环境回退：规则一旦更新，
    旧版本只能用于复核已签批次，不能再产出新权重。
    """
    return CURRENT_RULE_VERSION


def is_known(version: str) -> bool:
    return str(version) in RULEBOOKS


def rules_for(version: str) -> tuple[dict, ...]:
    try:
        return RULEBOOKS[str(version)]
    except KeyError:
        raise ValueError("UNKNOWN_RULE_VERSION") from None


def rulebook_digest(version: str) -> str:
    return canonical_digest(list(rules_for(version)))


def matches(rule: dict, project: dict, excluded: set[str]) -> bool:
    code = rule["code"]
    if code == "BLACKLIST":
        return bool(project.get("blacklisted", False))
    if code == "LOW_SCORE":
        score = project.get("score", 0)
        return score is not None and score < 60
    if code == "EXCLUDED_PROJECT":
        return str(project["id"]) in excluded
    if code == "RURAL":
        return project.get("region") == "rural"
    if code == "DEFAULT":
        return True
    raise ValueError("UNKNOWN_RULE_CODE")


def basis_digest(decisions) -> str:
    """资格依据摘要：只取影响结论的字段，对输入顺序不敏感。"""
    basis = [
        {
            "id": str(item["id"]),
            "eligible": bool(item["eligible"]),
            "reason": item.get("reason"),
            "rule_version": item.get("rule_version"),
        }
        for item in decisions
    ]
    return canonical_digest(sorted(basis, key=lambda item: item["id"]))


def eligible_ids(decisions) -> set[str]:
    return {str(item["id"]) for item in decisions if item["eligible"]}


def weight_set_digest(rule_version: str, basis_digest, entries) -> str:
    return canonical_digest(
        {
            "rule_version": str(rule_version),
            "rulebook_digest": rulebook_digest(rule_version),
            "basis_digest": basis_digest,
            "entries": [
                {"id": str(x["id"]), "weight": str(x["weight"]), "share": str(x["share"])}
                for x in sorted(entries, key=lambda x: str(x["id"]))
            ],
        }
    )


def weight_set_is_current(weight_set: dict | None, version: str | None = None) -> bool:
    """权重集是否仍可用于未签批次。

    规则更新（版本号或规则清单变化）后，旧权重集一律失效；
    即使项目已从名单剔除，也不能沿用旧权重的分摊结果。
    摘要必须与内容自洽，手工改写条目同样视为失效。
    """
    if not weight_set:
        return False
    current = str(version or current_version())
    if str(weight_set.get("rule_version")) != current:
        return False
    if weight_set.get("rulebook_digest") != rulebook_digest(current):
        return False
    if not weight_set.get("basis_digest") or not weight_set.get("entries"):
        return False
    expected = weight_set_digest(current, weight_set["basis_digest"], weight_set["entries"])
    return str(weight_set.get("weight_set_digest")) == expected
