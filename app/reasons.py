REASONS = {
    "BAD_COLUMNS": "字段数量不符",
    "EMPTY_VALUE": "必要值为空",
    "DUPLICATE_CONFLICT": "同一业务键取值冲突",
    "TRUNCATED": "尾记录不完整",
    "INVALID_VALUE": "值不符合定义",
    "INVALID_UNIT": "计量单位未登记",
    "STALE_VERSION": "提交版本已过期",
    "NEGATIVE_WEIGHT": "权重不得为负",
    "ZERO_WEIGHT_GROUP": "权重合计为零，无法归一",
    "STALE_WEIGHT": "权重依据已过期，请按当前资格规则重新测算",
    "MISSING_WEIGHT_SET": "缺少权重集，请先测算权重",
    "MISSING_DECISIONS": "缺少资格判定，请先运行资格校验",
    "EMPTY_WEIGHT_SET": "权重集为空，无法分摊",
    "MISSING_CAP": "权重项目缺少封顶金额",
    "NOT_ELIGIBLE_PROJECT": "被剔除的项目不得参与分摊",
    "UNKNOWN_RULE_VERSION": "未登记的资格规则版本",
    "UNKNOWN_RULE_CODE": "未登记的资格规则条目",
    "RULE_CONFLICT": "同一优先级规则结论冲突",
    "NO_RULE_MATCHED": "没有命中任何资格规则",
    "RULEBOOK_MISMATCH": "复核依据与登记规则不一致",
    "MISSING_STORE": "缺少留档存储，无法签批",
    "NOT_FOUND": "没有找到对应的签批留档",
    "DUPLICATE_APPROVAL": "同一批次已签批且依据不同，请走更正流程",
}

def reason(code: str) -> str:
    return REASONS.get(code, "未登记原因")
