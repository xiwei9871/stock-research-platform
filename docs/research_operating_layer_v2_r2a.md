# Research Operating Layer V2 R2A 运维说明

更新日期：2026-07-19

## Purpose

R2A 建立只服务于产业层研究的证据采集基线：从 Industry Evidence Requirement 生成定向 Search Plan，导入来源发现结果，安全抓取并保存原始资料，规范化 HTML、PDF、CSV、JSON 和纯文本，评价来源独立性、新鲜度、冲突与命题级证据作用，最后审计 Industry Design Gate。

R2A 的研究层固定为 `industry_research`。它回答“产业怎样运行、需要什么证据、产业约束是否真实”，不回答“哪家公司最好”或“哪只股票值得投资”。

## R1 And R2A Separation

- R1 位于 `artifacts/research_projects/v2/`，保存四个 research-design pilot，是冻结的上游基线。
- R2A 位于 `artifacts/research_projects/v2_1/`，保存四个独立 Industry Project 及证据获取对象。
- 每个 R2A version 都以 `upstream_research_versions` 引用指定 R1 version ID 和内容哈希；R2A 不拥有、不改写也不迁移 R1。
- R2A 的 loader、schema、CLI 和测试都位于 `research_project_v2_1` 命名空间；根 CLI 只增加原始参数委派。
- R2A 不修改 V1 Theme Research、Technology Industry Catalog、Dashboard、API 或数据库。

## Artifact Layout

```text
artifacts/research_projects/v2_1/
├── schema/                         # v2.1 JSON Schema
├── projects/
│   └── <project_slug>/
│       ├── project.json            # 稳定身份和版本指针
│       ├── version_manifest.jsonl  # append-only 版本清单
│       └── versions/
│           └── v<semver>.json      # 不可变完整快照
├── evidence/
│   ├── discovery/                  # 不可变来源发现批次
│   ├── raw/<sha-prefix>/           # 按 SHA-256 寻址的原始字节
│   ├── metadata/                   # 抓取事件与来源元数据
│   ├── normalized/                 # 规范化文档
│   └── assessments/                # 命题级证据评价
├── index/
│   └── research_project_index_v2_1.json  # 可重建缓存
└── fixtures/                       # 测试输入，不属于正式研究资产
```

CLI 不递归猜测任意 JSON 的含义。每类对象都有固定目录、artifact kind、schema 与机器可验证身份。

## Layered Identity And Versions

- `research_project` 是长期稳定身份；`research_version` 是某一时点的不可变完整快照。
- 文件名 `v<semantic_version>.json`、`version_id`、`project_id` 和项目目录 slug 必须一致。
- 同一对象语义不变时跨版本保留 ID；语义实质变化时创建新 ID并通过 relation/supersedes 记录关系。
- version 文件一旦创建不得覆盖。历史对象不得从旧 version 删除；新 version 只能标记 retired、superseded 或 removed-from-scope。
- `version_manifest.jsonl` 只追加，不重写历史行；index 是可重建缓存，不是身份或历史事实的权威来源。
- discovery batch、raw、metadata、normalized document 和 assessment 均采用内容派生身份并实行 write-once。相同内容可幂等复用，不同内容占用同一路径时必须失败。
- `project.json` 的关键指针只能由受锁定的维护事务更新；维护从读取、校验到发布使用同一排他锁，reader 使用共享锁，避免观察到半更新状态。
- 所有持久化路径必须留在 managed root 内，拒绝软链接、路径穿越、非常规文件和发布后的内容漂移。

## Industry Evidence Requirements

Evidence Requirement 描述“为了回答一个产业问题、命题、因果边或项目判断，需要什么证据”，而不是预先宣告结论。Requirement 可以绑定问题、待验证命题或产业研究对象，记录证据角色、期望来源类别、时效要求、独立性要求和验收条件。

四个 pilot 仅处于研究设计阶段：可以定义问题、hypothesis、证据需求和验证计划，但不得把 requirement 或背景引用解释成已支持命题。

## Search Plans

Search Plan 把 requirement 编译为可审计的查询集合。每个 requirement 必须被至少一个 plan 覆盖；每个 plan 必须包含 primary query 和 counter-evidence query，并记录 query ID、语言、来源类别、时间范围、包含/排除术语、状态与 provenance。

Search Plan 的 Router 和查询只服务产业事实。查询输出不得请求公司排名、股票推荐、目标价、估值或投资判断。`search-plan` 命令只读并报告覆盖情况，不写 artifact。

## Source Discovery

R2A 不内置搜索引擎账号或自动网络搜索。`discover` 接受一个已存 Search Plan JSON 和一个外部 provider 导出的 JSON 结果，完成：

- URL 规范化、确定性排序与去重；
- 来源类别、publisher、发布日期、query/rank 和 provenance 归一化；
- 过滤股票观点、荐股、目标价和公司排名内容；
- 生成不可变 discovery batch；
- 默认只预览，只有显式 `--write` 才保存到 `evidence/discovery/`。

## Secure Snapshots

`snapshot` 的安全默认值是：

- 只允许不含凭证的 `http`/`https` URL；
- DNS 任一答案为 loopback、private、link-local、reserved、multicast、unspecified、CGNAT 或其他非 global 地址时拒绝；
- 每一次请求和每一次 redirect 都重新解析、重新校验，实际 peer IP 必须属于该次批准地址集合，以阻止 SSRF、DNS rebinding 和代理绕过；
- requests 自动 redirect 关闭，由 snapshot 层处理，最多 5 次，拒绝循环、缺失/重复 Location 和不安全目标；
- 单次请求 timeout 为 20 秒；
- 最大响应体为 25 MiB，同时检查 `Content-Length` 和实际流量；
- 只接受 `application/pdf`、`text/html`、`text/plain`、`application/json`、`text/csv`；
- 只接受 2xx 最终响应，拒绝声明长度与实收字节不一致；
- 发送 `Accept-Encoding: identity`，不保存 cookie、authorization 或任意响应头，只保存审核过的 header allowlist；
- 原始内容按 SHA-256 寻址，metadata 记录原始/最终 URL、redirect chain、peer 已验证后的 fetch 结果、字节数、media type、时间和 provenance；
- 默认只预览。显式 `--write` 才发布 raw 与 metadata，发布为原子、不可变且 symlink-safe。

## Document Normalization

`parse` 从已保存并通过哈希校验的 evidence artifact 读取原始字节，按 media type 选择 HTML、PDF、CSV、JSON 或 text parser。规范化文档保存 parser/version、title、section、可审计 locator、section hash、document hash、warnings、时间和 provenance。

HTML 保留结构位置；PDF 保留页码；CSV/JSON 保留行、字段或结构定位；解析限制和 unsupported media 返回明确错误。默认预览，`--write` 才写入 `evidence/normalized/`，且不会修改 project version。

## Independence And Freshness

R2A 把“存在多个 URL”与“存在多个独立证据源”分开。独立性判断结合内容哈希、共同上游、publisher family、转载关系和 section 重合；不确定时采用保守的 `unknown`，不把转载循环计为独立支持。

新鲜度使用来源日期、观察时点和 requirement 的 freshness policy 明确计算，不能用抓取时间伪装发布日期。支持和反对材料来自独立 source family 且实质冲突时，必须显式报告 `material_conflict`；证据不足、过期或来源关系不明也必须可见且确定性输出。

## Industry Evidence Assessment

Evidence Assessment 是来源对具体 target 的证据作用记录，包含 artifact、normalized document、精确 locator、support/opposition/quantification 等角色、强度、时效性、独立性、冲突与人工 review status。

- 来源挂在项目上不等于证明命题；实质性支持或反对必须通过 assessment。
- assessment 只能引用已存且哈希、identity、locator 一致的 artifact/document。
- 新建 assessment 永远不会自动修改 claim status、confidence 或 project conclusion。
- `--write` 只新增不可变 assessment artifact，不改写 version。
- 未审核或未经 assessment 的引用不计入任何后续 Publication Gate。

## Industry Design Gate

Industry Design Gate 对已存 project/version 和其 R1 lineage 执行 12 项结构检查，包括产业层身份、范围、问题、hypothesis、requirement 覆盖、counter-evidence 搜索、来源类别、provenance、无下游研究输出等。四个 pilot 只要求通过 Design Gate，不代表 Evidence Readiness、Bottleneck Readiness 或 Publication Gate 已通过。

输出字段语义必须严格区分：

- `status` 是当前 CLI 操作或 Gate 的机器结果；`pass` 只表示该操作定义的检查通过。
- `verified=true` 只表示 `verified_scope=stored_project_version_and_lineage_only` 范围内的存储对象、身份、哈希和 lineage 被验证。
- `verified` 不表示 hypothesis 已被支持，不表示证据充分，不表示产业瓶颈已成立，更不表示公司或投资结论。
- `conclusion_status=unavailable` 和 `investment_status=not_assessed` 是当前四个 pilot 的预期状态。

## CLI Commands

所有命令都通过根入口执行，成功与失败均输出稳定 UTF-8 JSON，不输出 traceback。以下是每个 subcommand 的完整示例：

```bash
rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli research-project-v2-1 list

rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli research-project-v2-1 show --project ai_compute_pcb_industry_bottleneck --version 0.1.0

rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli research-project-v2-1 validate --all

rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli research-project-v2-1 gate --project ai_compute_pcb_industry_bottleneck --version 0.1.0 --gate industry-design

rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli research-project-v2-1 search-plan --project ai_compute_pcb_industry_bottleneck --version 0.1.0

rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli research-project-v2-1 discover --search-plan work/r2a/search_plan.json --results artifacts/research_projects/v2_1/fixtures/discovery/imported_results.json --discovered-at 2026-07-19T00:00:00Z --agent-run-id operator:r2a:discover:001 --write

rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli research-project-v2-1 snapshot --candidate work/r2a/source_candidate.json --fetched-at 2026-07-19T00:05:00Z --agent-run-id operator:r2a:snapshot:001 --write

rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli research-project-v2-1 parse --artifact-id evidence_artifact:0123456789abcdef01234567 --parsed-at 2026-07-19T00:10:00Z --agent-run-id operator:r2a:parse:001 --write

rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli research-project-v2-1 assess --assessment work/r2a/industry_evidence_assessment.json --write

rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli research-project-v2-1 audit --project ai_compute_pcb_industry_bottleneck --version 0.1.0

rtk env PYTHONPATH=src /Users/xiwei/stock_research/.venv/bin/python -m stock_research.cli research-project-v2-1 rebuild-index --write
```

`discover`、`snapshot`、`parse` 和 `assess` 在没有 `--write` 时是安全预览。示例中的 `work/r2a/*.json` 必须由 operator 审核后提供；artifact ID 必须替换为前一步实际产生的 ID。不要对不可信候选直接使用 `--write`。

## Exit Codes

| Exit | Meaning |
|---:|---|
| 0 | success、pass、pass_with_warnings 或 not_applicable；不代表研究结论成立 |
| 2 | CLI 输入、JSON Schema 或 semantic validation 失败 |
| 3 | evidence audit 或 Search Plan coverage 失败 |
| 4 | Industry Gate 失败 |
| 5 | hash、manifest、managed path、storage identity 或 immutability 违规 |
| 6 | project、version、artifact、document 或 managed file 不存在 |
| 8 | discovery provider、网络、SSRF、redirect、media 或 snapshot fetch 失败 |
| 9 | parser、normalization、unsupported media 或解析限制失败 |
| 10 | 非预期 runtime 或 I/O/storage failure |

失败 JSON 固定包含 `error.code`、`error.message` 和 `error.details`。operator 必须同时检查 exit code 和 JSON `status`，不能只检查 stdout 是否存在。

## Adding An Industry Project

1. 从一个已审核 R1 pilot version 或其他允许的上游研究版本开始，记录精确 version ID、SHA-256、引用角色和时间。
2. 创建唯一 project slug 与 `research_layer=industry_research` identity，不得使用 `company_capture` 或 `stock_evaluation`。
3. 在 `versions/v0.1.0.json` 创建完整 research-design snapshot；所有对象的 `created_in_version` 必须等于当前 version ID。
4. 定义产业范围、Router、问题树、hypothesis、counter/alternative claim、Evidence Requirements 和验证计划。
5. 为每个 requirement 编译 Search Plan，确认 primary/counter 查询、来源类别、独立性与 freshness 要求完整。
6. 运行 `validate`、`search-plan`、`gate` 和 `audit`；修复所有结构失败，不得通过删除反方要求来“过 Gate”。
7. 用 `rebuild-index` dry-run 审查计划变更；确认后显式 `--write`。再次运行 write 必须幂等且无 artifact diff。
8. 提交前解析全部 JSON/JSONL、运行 forbidden-language scan、R2A/R1/V1 回归和 commit-attributed scope guard。

## R2A Non-goals

以下 checklist 对正式 Industry Project、Search Plan、assessment 和 CLI 写入 artifact 全部适用：

- [ ] 不生成 company candidate 或候选公司清单；公司只能作为工程、产能、认证或供应证据来源元数据出现。
- [ ] 不生成 company rating、Company Industrial Capability Rating 或公司排名。
- [ ] 不读取、保存或评价 stock price、target price、估值、市场预期或交易拥挤度。
- [ ] 不生成 stock rating、股票推荐、买入/卖出意见、watchlist candidate 或 strategy hypothesis。
- [ ] 不形成投资判断、收益预测或组合建议。
- [ ] 不把 source、requirement、search hit 或 assessment 自动升级为 supported claim。
- [ ] 不开始 R2B bottleneck 结论、R3 company mapping、R4 value capture rating 或 R5 stock evaluation。

## Production Migration Prohibition

R2A 是独立 artifact baseline。本阶段明确禁止：

- 执行或创建生产数据库 migration、生产表或 shadow import；
- 修改现有数据库 schema、API route、Dashboard 或 `/theme-research` 行为；
- 向 V1/R1 回写、迁移、覆盖或自动 promotion；
- 让 research_case、review、publication、watchlist 或 strategy 成为 loader 运行依赖。

任何数据库映射、API 或 Workbench 工作必须等待后续阶段的单独设计、人工确认和生产授权。

## Verification Evidence

最终 R2A 验证在 2026-07-19 执行，结果如下：

- R2A focused suite：`966 passed, 10 warnings`；
- 计划指定的 R1 compatibility glob：`1199 passed, 10 warnings`；该 glob 按 shell 规则同时包含 `v2_1` 测试；
- 选定 V1 Theme/Company/Catalog/Dashboard regression suite：`380 passed, 8 warnings`；
- CLI focused acceptance：`49 passed, 8 warnings`；
- 实际 CLI：list、show、validate、gate、search-plan、audit、rebuild dry-run、第一次 write、第二次 write 均 exit `0`；
- imported discovery、fake-transport snapshot、parse fixture、assessment validation 和失败 exit envelope 均由 CLI focused acceptance 覆盖；
- `40` 个 JSON 与 `14` 个 JSONL 全部通过 `jq empty`；
- 正式 projects/index/discovery/document fixtures 的 downstream object key scan 为零；recommendation term 的文字命中只存在于 `scope.excluded_scope` 和 Search Plan `excluded_terms`，其语义是禁止输出和过滤来源，不是推荐内容；
- 两次 `rebuild-index --write` 后，`git diff --exit-code -- artifacts/research_projects/v2_1` 为 `0`；
- scope guard 固定 `56` 个 approved full SHA，逐 commit 执行 `git cat-file` 和 `git diff-tree`，聚合 `86` 个 changed path，`31 passed`；共享分支并发提交不通过 `base..HEAD` 被吸收；
- 从 Task 1 parent 到当前 HEAD，R1 `v2`、V1 Theme Decomposition 与 Technology Industry Catalog byte diff 为零；R1 仍恰好四个项目；
- v2.1 index 恰好四个 `industry_research` 项目；每个 version 都通过 loader/lineage audit，引用预期 R1 version ID 和 SHA-256；
- 四个项目均只有 `hypothesis/under_test` claim、零 Industry Evidence Assessment、`conclusion_status=unavailable`、`investment_status=not_assessed`；
- scope guard 与提交内容确认没有生产 migration、API、Dashboard、数据库、company rating 或 stock rating 改动。

warning 均为既有的 Python 3.14 `py_mini_racer` layout deprecation 与 `jsonschema.RefResolver` deprecation；R2A 没有引入新的 warning 类别。上述证据只关闭 R2A，不表示 R2B、R3、R4 或 R5 已开始或完成。
