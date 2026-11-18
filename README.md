# 专项资金分摊与舍入尾差复核

面向一线复核人员的单服务数据工作台。样例数据随仓库提供，结论保留行号、原因码和原值。

## 业务模块

- M1 预算采信：`/api/budgets/import`
- M2 资格校验：`/api/eligibility/evaluate`
- M3 权重测算：`/api/weights/calculate`
- M4 金额分摊：`/api/allocations/calculate`
- M5 尾差裁决：`/api/remainders/resolve`
- M6 批次复核：`/api/export/allocations.csv`

## 核心规则

先迭代封顶再按有效权重分配，最后用最大余额法落到分；输入顺序变化不得改变结果。

资格规则更新（`app/rulebook.py`）后：

- 未签批次必须按当前规则重新做资格校验与权重测算，旧权重集一律判为 `STALE_WEIGHT`，不能继续用于分摊或签批；
- 已签批次按签批当天留档的资格与权重复核，不因规则更新改写结论；
- 被剔除的项目即使还带着旧权重，也不得再分到款（`NOT_ELIGIBLE_PROJECT`）。

## 签批与复核

- `POST /api/runs/approve`：签批留档，快照包含当日规则版本、规则清单摘要、资格依据与权重集；同一批次重试只返回原 `run_id`，不重复留档。
- `GET /api/runs/{batch_key}/recheck`：按签批当天快照复核已签批次。
- `/runs` 页面展示当前待签依据与全部已签批留档。

## 启动

```bash
docker compose up --build
```

浏览器访问 `http://localhost:18213`。运行测试：

```bash
docker compose exec -T app pytest -q
```

## 样例流程

依次运行六个模块；最后在批次页复核输入、有效、隔离与输出合计。同一输入摘要重复执行时复用原 `run_id`。

## 已知不覆盖

不处理加密文件与需要外部密钥的对象；不连接真实生产存储。
