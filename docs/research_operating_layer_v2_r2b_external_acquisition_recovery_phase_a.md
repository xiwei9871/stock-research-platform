# Research Operating Layer V2 R2B — External Evidence Acquisition Recovery Phase A

日期：2026-07-20  
基线 HEAD：`fd057e20ca1d81129ff39f0a253fe122acca99c2`  
范围：只读诊断、能力审计和最小恢复设计；未实现 provider，未运行 AI PCB acquisition smoke batch。

机器可读诊断：

`artifacts/research_projects/v2_1/acquisition/diagnostics/r2b_external_acquisition_phase_a_2026-07-20.json`

## 1. 当前失败根因

外部资料获取不是单一的“无网络”问题，而是三个相互独立的通道状态：

1. 主机 DNS、TLS 和直接 HTTP/HTTPS 出口当前正常；
2. 现有 `RequestsFetchTransport` 会通过 Python/urllib 的系统代理发现机制继承 macOS 系统代理，即使 `HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY` 全部未设置；
3. 请求经过私网代理后，实际 socket peer 是 `192.168.3.x`。现有 SSRF 防护禁止私网 peer，因此以 `RESEARCH_PROJECT_V2_1_FETCH_PEER_DENIED` 正确失败；
4. 显式关闭环境和系统代理发现（诊断中使用 `requests.Session.trust_env=False`）后，现有 snapshot、原始文件存储、SHA-256 和 normalization 流程可以完整处理 HTML 与 PDF；
5. 配置的搜索服务仍对 search 和 direct-open 两类调用返回 HTTP 404；
6. 内置浏览器绑定不可用，但本机 Python Playwright 1.60.0 和 Chromium runtime 可启动；
7. Docling 2.110.0 已安装，但尚未接入 Research Project V2.1 的标准 normalization pipeline。

因此当前主要根因不是 DNS、TLS 或公网出口，而是：

> HTTP transport 没有显式 request/proxy mode，导致系统代理被静默继承；安全层随后无法把私网代理 peer 当作目标站点 peer 验证。

当前主要 `failure_code` 应记录为 `security_policy_blocked`，底层错误为 `FETCH_PEER_DENIED`。搜索服务单独记录为 `search_provider_error`，不能与 HTTP transport 故障合并。

## 2. Direct 网络状态

| 检查 | 结果 |
|---|---|
| DNS：example.com | 通过，返回公开 IPv4/IPv6 |
| TLS | 通过，TLS 1.3，证书验证正常 |
| HTTPS HTML | 200，`text/html` |
| HTTP HTML | 200，`text/html` |
| 公开 PDF | 200，`application/pdf`，13,264 bytes |
| PDF SHA-256 | `3df79d34abbca99308e79cb94461c1893582604d68329a41fd4bec1885e6adb4` |
| 重定向 | 通过，1 次 redirect 后 200 |
| 现有 snapshot + 显式 direct | HTML 与 PDF 均成功 |
| normalization | HTML 使用 `stdlib.html.parser`；PDF 使用 `pypdf` |

一个备用重定向诊断站点 `httpbin.org` 超时，分类为 `connection_timeout`；独立的 `httpbingo.org` 重定向测试通过，因此不能把该单点超时解释为总体重定向能力失败。

结论：direct automated acquisition 可以恢复，不需要更换 HTTP 库或建立 crawler。

## 3. Proxy 网络状态

环境变量状态：

- `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY`：未设置；
- 小写同名变量：未设置；
- `NO_PROXY`：未设置。

macOS 系统网络设置中存在 HTTP、HTTPS 和 SOCKS 代理。报告只保存脱敏 endpoint `192.168.3.x:789x`，没有发现代理凭据，也未保存完整地址、密码或 Cookie。

Python `requests` 的默认 `trust_env=True` 会通过 urllib 读取这些系统代理：

```text
requests default
→ macOS system proxy
→ private proxy peer
→ existing SSRF peer validation
→ security_policy_blocked / FETCH_PEER_DENIED
```

`trust_env=False` 时实际 peer 恢复为 DNS 返回的公开地址，snapshot 成功。

建议 Phase B 将模式显式化：

- `proxy_mode=direct`：禁用环境和系统代理发现；
- `proxy_mode=environment`：只在用户明确选择时启用，并记录解析后的脱敏 proxy endpoint；
- 不允许 direct 失败后静默切换 proxy；
- proxy 模式需要独立安全设计，因为通过代理时无法再用 socket peer 等同目标站点 IP；在没有可信代理 allowlist 前，proxy fetch 应返回 `security_policy_blocked`，而不是降低 SSRF 门槛。

## 4. 搜索 Provider 状态

配置的搜索服务对以下两类调用均稳定返回 HTTP 404：

- search query；
- direct URL open。

响应没有 401/403、429、quota 或 credential 信号，因此当前不能分类为：

- `search_auth_error`；
- `search_quota_exceeded`；
- `rate_limited`。

当前准确分类是 `search_provider_error`，推断位置是 provider gateway/route，而非查询内容或本机网络。

代码库内没有另一个透明、已配置、可审计的在线搜索 provider。已有：

- `ImportedJsonDiscoveryProvider`：离线导入显式搜索结果；
- `DirectUrlDiscoveryProvider`：由已知 URL 生成 candidate；
- `DiscoveryProvider` protocol 和 canonical discovery batch。

因此 Phase B 不应匆忙接入来源不透明的替代搜索接口。搜索不可用时仍可通过官方目录 URL、用户提供 URL、离线导入搜索结果和 local/manual import 解锁研究。

## 5. Browser Runtime 状态

| 能力 | 状态 |
|---|---|
| Codex in-app browser binding | unavailable |
| Safari 应用 | 存在 |
| Python Playwright package | 已安装 |
| Playwright Chromium runtime | 可启动，headless smoke 通过 |
| Playwright WebKit runtime | 已安装 |

这表示 browser provider 技术上可选，但不是恢复 direct acquisition 的前置条件。

Phase B 推荐只实现：

- runtime detection；
- provider contract；
- `browser_runtime_unavailable` 状态；
- 可选的 headless adapter smoke。

不安装新浏览器、不接管登录态、不读取 Cookie/local storage、不绕过 CAPTCHA、付费墙或访问控制。

## 6. 可复用的现有模块

### Source Discovery

`src/stock_research/research_project_v2_1/discovery.py`

已经提供：

- `DiscoveryProvider` protocol；
- imported JSON provider；
- direct URL provider；
- URL canonicalization；
- candidate stable ID；
- canonical URL dedup；
- search batch immutable hash；
- snippet 仅作为 discovery metadata；
- stock-opinion source policy guard。

### HTTP Snapshot

`src/stock_research/research_project_v2_1/snapshot.py`

已经提供：

- GET；
- manual redirect handling 和 loop/limit 检查；
- timeout；
- streamed body；
- 25 MiB 默认上限；
- MIME allowlist；
- Content-Length 校验；
- SHA-256；
- content-addressed raw path；
- temporary file、fsync、原子发布；
- exact-content dedup；
- immutable metadata；
- DNS rebinding/SSRF peer 检查；
- partial temporary cleanup。

### Normalization

`normalize.py` 与 `parsers.py` 已支持：

- HTML；
- PDF（pypdf）；
- UTF-8 TXT；
- Markdown 可按 `text/plain` 导入；
- JSON；
- CSV；
- locator；
- section hash；
- parser limits；
- normalized document immutable storage。

### Docling

`data_to_brief_docling_parser_poc.py` 已有：

- Docling runtime detection；
- `DocumentConverter` 调用；
- markdown/JSON/table 提取；
- pypdf fallback 经验。

但该模块属于早期专项 pipeline，输出模型与 V2.1 normalized document 不一致，不能直接作为 provider 依赖。Phase B 可复用适配思路，不应直接调用整个股票批处理流程。

### 其他可借鉴模块

- `eastmoney_http.py`：显式 `--noproxy`、bounded retry 和 timeout，但基于 subprocess/curl，适合作为行为参考，不应成为主 provider；
- `tech_bottleneck_review_universe_report_pdf_platform_import.py`：本地 PDF 路径、来源说明和版权备注经验，但当前面向数据库导入，不符合本任务 migration-free artifact layer；
- 当前 CLI 已有 `discover`、`snapshot`、`parse`、`assess`、`audit`，可以扩展而不是重建平行 CLI。

## 7. 缺失能力

真实缺口如下：

1. 没有一等 `acquisition_attempt`；失败只能抛异常，无法形成 append-only 审计记录；
2. 没有统一 failure taxonomy 映射；
3. HTTP transport 没有显式 direct/environment proxy mode；
4. 没有 bounded retry/backoff 和 retry count 记录；
5. headers 固定，不能受控配置 User-Agent/Accept；
6. 非 2xx 响应不会形成 acquisition attempt artifact；
7. 没有正式 local/manual import provider；
8. evidence artifact 没有 acquisition attempt ID、source title、publisher、published/accessed 分离和 license/access note；
9. 没有 browser provider contract/runtime detector；
10. 没有在线 search adapter 的 provider-unavailable 记录；
11. 没有 acquisition checkpoint artifact；
12. exact hash dedup 已有，但 redirect alias 与 canonical URL alias 尚未形成独立关系记录；
13. Docling 已安装但未适配 V2 normalization contract。

## 8. 推荐 Provider 架构

### 方案 A：扩展现有 R2A acquisition pipeline（推荐）

围绕 `discovery.py`、`snapshot.py`、`normalize.py` 增加薄的 acquisition orchestration：

```text
Evidence Requirement / Search Plan
→ DiscoveryProvider.search()
→ SourceCandidate
→ AcquisitionProvider.acquire()
→ AcquisitionAttempt
→ Raw Evidence Artifact
→ NormalizedDocument
→ pending_assessment
```

Provider 分为：

- `local_file_provider`；
- `direct_http_provider`；
- `search_discovery_provider`；
- `optional_browser_provider`。

优点：复用现有安全存储、哈希、parser、审计和 CLI；改动最小。缺点：需要拆出 `RequestsFetchTransport` 的 session/proxy 配置，并新增 attempt schema。

### 方案 B：以 curl subprocess 作为 HTTP provider

优点：当前 direct curl 已验证可用，`--noproxy` 和 retry 行为清晰。缺点：会复制 Python snapshot 已有的 header、peer、stream、storage 和错误处理逻辑；跨平台和测试成本更高。

不推荐作为主路径，只可保留为环境 doctor 的独立诊断探针。

### 方案 C：browser-first acquisition

优点：可以覆盖 JavaScript 页面。缺点：运行成本、失败面、页面不确定性和合规风险最高；不适合作为 HTML/PDF 获取的基础通道。

只保留 optional adapter，不作为恢复主路径。

## 9. Failure Taxonomy

Phase B 至少实现用户指定的全部 failure code，并增加当前诊断真实需要的 `security_policy_blocked`：

```text
dns_failure
connection_refused
connection_timeout
proxy_unreachable
proxy_auth_required
tls_failure
http_error
rate_limited
search_provider_error
search_auth_error
search_quota_exceeded
robots_disallowed
login_required
paywalled
browser_runtime_unavailable
javascript_required
invalid_mime_type
empty_content
checksum_failure
unsupported_format
manually_unavailable
security_policy_blocked
unknown_failure
```

映射原则：

- exception type、HTTP status 和 provider response 先标准化，再生成 failure code；
- 401/403 不自动等于 paywall，只有页面或 provider 明确信号时才使用 `login_required` / `paywalled`；
- 404/5xx 使用 `http_error`，搜索 provider gateway 自身错误使用 `search_provider_error`；
- 429 使用 `rate_limited`；
- 搜索服务只有明确 credential/quota 信号时才使用 auth/quota code；
- robots 或访问控制不允许自动绕过；
- 无法可靠分类时使用 `unknown_failure`，保留脱敏 error summary。

## 10. 最小 Schema Gap

不应修改或重新解释已经用于 v0.2.0/v0.2.1 的 Schema 2.2.0 文件。

Phase B 推荐新增向后兼容的 Schema 2.3.0 standalone artifact family：

1. `acquisition_attempt_v2_3`：保存 attempt identity、candidate、provider、request/proxy mode、时间、status、failure code、HTTP/MIME/bytes/elapsed/retry 和 error summary；
2. `evidence_artifact_v2_3`：保留现有 immutable raw artifact 字段，并增加 acquisition attempt、source title、publisher、published_at、accessed_at、license/access note；
3. `manual_import_request_v2_3`：保存来源说明、原始 URL、导入 actor、文件 metadata 和 locator capability；
4. `acquisition_checkpoint_v2_3`：引用 attempt、artifact、normalized document 和 pending-assessment 状态，不成为 research version；
5. `provider_diagnostic_v2_3`：机器可读 doctor 输出。

Loader 必须继续支持 2.1、2.2。`v0.2.0` 和 `v0.2.1` 不变。未来 `v0.2.2` 是否使用 research schema 2.3.0，在 smoke batch 和证据采集范围确认后再决定。

## 11. 推荐 CLI

优先在 `research-project-v2-1` 下新增一个 `acquisition` command group，避免平行顶级命令爆炸：

```text
research-project-v2-1 acquisition doctor
research-project-v2-1 acquisition fetch
research-project-v2-1 acquisition import
research-project-v2-1 acquisition show-attempt
research-project-v2-1 acquisition smoke
```

共同参数：

- `--project`；
- `--version`；
- `--dry-run`；
- `--timeout-seconds`；
- `--output`；
- machine-readable JSON；
- 无 silent fallback。

`fetch` 增加：

- `--provider direct-http|browser`；
- `--proxy-mode direct|environment`；
- bounded retry；
- explicit candidate/input。

本任务不把 `assess` 合并进 acquisition；成功获取后的最终状态最多到 `pending_assessment`。

## 12. Phase B 精确文件范围

建议新增：

```text
src/stock_research/research_project_v2_1/acquisition.py
src/stock_research/research_project_v2_1/acquisition_failures.py
src/stock_research/research_project_v2_1/acquisition_doctor.py
src/stock_research/research_project_v2_1/manual_import.py
src/stock_research/research_project_v2_1/browser_runtime.py
artifacts/research_projects/v2_1/schema/acquisition_attempt_v2_3.schema.json
artifacts/research_projects/v2_1/schema/evidence_artifact_v2_3.schema.json
artifacts/research_projects/v2_1/schema/manual_import_request_v2_3.schema.json
artifacts/research_projects/v2_1/schema/acquisition_checkpoint_v2_3.schema.json
artifacts/research_projects/v2_1/schema/provider_diagnostic_v2_3.schema.json
tests/test_research_project_v2_1_acquisition_failures.py
tests/test_research_project_v2_1_acquisition_doctor.py
tests/test_research_project_v2_1_acquisition_http.py
tests/test_research_project_v2_1_acquisition_import.py
tests/test_research_project_v2_1_acquisition_browser.py
tests/test_research_project_v2_1_acquisition_cli.py
```

建议最小修改：

```text
src/stock_research/research_project_v2_1/snapshot.py
src/stock_research/research_project_v2_1/normalize.py
src/stock_research/research_project_v2_1/layout.py
src/stock_research/research_project_v2_1/schema.py
src/stock_research/research_project_v2_1/cli.py
tests/test_research_project_v2_1_r2b_scope_guard.py
```

禁止范围保持不变：V1、27 个主题、其他三个 Pilot、Dashboard、API、数据库、watchlist 和 strategy。

## 13. 测试范围

### Offline deterministic tests

- provider contract；
- complete failure-code classification；
- explicit direct vs environment proxy behavior；
- no silent fallback；
- bounded retries；
- redirect chain；
- HTTP status preservation；
- MIME sniff/header conflict；
- streamed max-size enforcement；
- temp cleanup and atomic commit；
- SHA-256 和 exact-content dedup；
- local import metadata/provenance；
- duplicate local content；
- raw artifact immutability；
- normalization failure preserves raw artifact；
- browser runtime available/unavailable；
- schema validation；
- CLI JSON and exit codes；
- credential redaction。

### Optional online smoke

- 标记 `network_required`；
- 默认不运行；
- 每个请求有短 timeout；
- 使用稳定公共 HTML/PDF endpoint；
- 不断言易变化正文；
- 服务波动输出诊断结果，不作为离线回归失败。

### Manual environment diagnostic

- 输出 JSON；
- 只记录 proxy 是否设置和脱敏 endpoint；
- 不保存 API key、Cookie、密码或完整 credential URL；
- 检测 DNS/TLS/direct/proxy/search/browser；
- 每项包含明确 failure code。

现有 1020 / 1253 / 449 / 23 测试不得依赖互联网。

## 14. 安全与合规边界

- 保留现有 SSRF public-address policy；
- direct 与 proxy 必须显式选择；
- 不允许 silent fallback；
- proxy 模式没有可信 allowlist 时 fail closed；
- 不读取或提交代理密码、API key、Cookie、浏览器 session storage；
- 不绕过登录、付费墙、CAPTCHA、robots 或访问控制；
- 不把 snippet、页面标题或 fetch 成功当作 Evidence Assessment；
- 非 2xx、解析失败和 access failure 都保留 attempt，但不生成成功 raw artifact；
- local import 要记录 license/access note；
- raw artifact immutable；
- normalization 可重跑，但不能覆盖 raw；
- search、HTTP、browser 每次尝试各有独立 attempt，不合并失败历史。

## 15. 是否能够恢复 Automated Acquisition

可以，但分两部分：

- Direct HTTP acquisition：可以恢复。现有 snapshot pipeline 已经通过显式 direct 诊断；Phase B 只需正式加入 request/proxy mode、attempt ledger、failure taxonomy 和 retry；
- Search discovery：当前不可恢复，provider gateway 持续 404。应保持 `provider_unavailable`，不要更换为来源不透明接口；
- Browser acquisition：可选 runtime 可用，但不是 direct 恢复前置条件。

因此 Stage A 可以在没有搜索 provider 的情况下，通过官方目录、已知一手 URL、用户提供 URL或 imported discovery JSON 开始小批量 acquisition。

## 16. Manual / Local Import 如何解锁研究

即使在线搜索继续不可用，正式 local import 可以完成：

```text
user/official URL metadata
→ local PDF/HTML/TXT/MD/JSON/CSV
→ bounded read + MIME validation
→ SHA-256
→ immutable raw artifact
→ normalization
→ pending_assessment
```

它不会自动满足 requirement，不会生成 assessment，也不会改变 bottleneck 状态。对于只有付费或不可访问版本的关键材料，记录 `paywalled` / `manually_unavailable`，不得用摘要填补。

## 17. 需要用户确认的决定

进入 Phase B 前需要确认：

1. 是否批准推荐方案 A：扩展现有 R2A snapshot/discovery/normalization，而不是 curl 或 browser-first；
2. 是否批准新增 Schema 2.3.0 standalone acquisition artifacts，并保持 2.1/2.2 完全不变；
3. 是否批准 Phase B 默认 `proxy_mode=direct`，environment proxy 必须显式选择且在可信代理安全规则完成前 fail closed；
4. 是否批准 browser provider 先只实现 runtime detection 和 optional adapter，不作为 smoke batch 必选通道；
5. 是否批准 Docling 仅作为可选 normalization adapter，默认继续使用现有 deterministic parser；
6. 是否批准 Phase B 文件范围和 offline/online 测试分层。

用户确认前，不开始 Phase B，不运行 AI PCB Stage A acquisition smoke，不生成 v0.2.2。
