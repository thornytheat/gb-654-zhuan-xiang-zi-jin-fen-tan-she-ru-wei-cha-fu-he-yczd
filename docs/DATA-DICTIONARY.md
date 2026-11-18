# 数据字典

| 字段 | 类型 | 可空 | 定义 |
|---|---|---:|---|
| `run_id` | string | 否 | 输入摘要派生的稳定运行编号 |
| `source_line` | integer | 否 | 原文件物理行号 |
| `reason_code` | string | 是 | 隔离或冲突的稳定原因码 |
| `raw_value` | string | 是 | 未归一的原始证据 |
| `normalized_value` | string | 是 | 按项目规则得到的值 |
| `rule_version` | string | 否 | 计算规则版本；资格规则版本固定登记在 `app/rulebook.py` |
| `rulebook_digest` | string | 否 | 该规则版本下规则清单的摘要，规则条目变化即变 |
| `basis_digest` | string | 是 | 资格依据摘要：项目、结论、原因与规则版本的规范化摘要，与输入顺序无关 |
| `weight_set_digest` | string | 是 | 权重集摘要：规则版本、规则清单摘要、资格依据摘要与权重条目共同决定 |
| `batch_key` | string | 否 | 批次业务键：有 `batch_id` 用批次号，否则用行内容摘要 |
| `snapshot_digest` | string | 是 | 签批留档快照的摘要，用于判断重试是否同一依据 |

## 权重集

权重集用于把资格结论接入分摊，结构为：

| 字段 | 类型 | 定义 |
|---|---|---|
| `rule_version` | string | 测算时的资格规则版本 |
| `rulebook_digest` | string | 测算时的规则清单摘要 |
| `basis_digest` | string | 测算所依据的资格结论摘要 |
| `weight_set_digest` | string | 上述内容与权重条目的总摘要 |
| `entries` | array | `{id, weight, share}`，只含通过资格校验的项目 |

分摊与签批前会重新校验上述摘要：规则版本、规则清单或条目内容任一不符，均判 `STALE_WEIGHT`，须按当前规则重新测算。

## 签批快照

签批留档固化签批当天的复核依据，包含 `batch_id`、`rule_version`、`rulebook_digest`、`basis_digest`、`weight_set_digest`、`eligibility`（逐项资格与原因）、`weights`（权重与份额）、`rows`、`allocated_total`、`approved`、`balanced`。已签批次复核只读该快照。

字符串编号逐字保留。金额与计量值用 `Decimal`。时间值带偏移并以 UTC 参与比较。区间统一采用左闭右开。
