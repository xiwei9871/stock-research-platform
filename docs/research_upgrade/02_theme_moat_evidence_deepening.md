# 02 — Theme Moat Evidence Deepening (M0.6, task D / M1 continuation)

Date: 2026-10-20. Branch: `audit/tech-strategy-m0-20261019` @ `1149c763`.
Extends `01_theme_competitive_moat_pilot.md` dossiers (英维克 002837.SZ liquid cooling;
北方华创 002371.SZ deposition/epitaxy) with the now-imported 100-report corpus.
All cited material remains `gated` / `unverified_research_lead` /
`pending_theme_mapping_review` — broker-derived second-hand evidence awaiting human
verification. No DB writes, no signal/admission changes.

## Verdict: PARTIAL — deepening continued; dossiers still honestly incomplete

## 1. 英维克 — liquid cooling / AI power

New corpus leads (page-cited, unverified):

| Dimension | New lead evidence | Status after deepening |
|---|---|---|
| Competitor landscape | 申菱环境 "液冷全方案出海先锋" (华鑫, 2026-10-12, p.2); 国金 (2026-10-10) pp.1–3: full-chain 风液同源 data-center cooling incl. liquid loop; 三花智控 2025 annual review (银河, 2026-03-24, pp.1–2): "数据中心液冷收入翻倍", refrigeration parts 185.85亿 rev / 28.77% GM | `unknown` → **`lead`** — named rivals w/ disclosed scale |
| Technology bypass risk | 大元泵业 report (华源, 2026-08-19, pp.11–12): 屏蔽泵 zero-leak, ≥60% shorter body, native 800V-HVDC CDU fit — claims NVIDIA Kyber CDU adoption & Google 2MW CDU confirmation; 磁悬浮离心压缩机 industry report (华源, 2026-07-28, pp.1,12): IPLV +42%, −30% motor power vs screw units | `unknown` → **`lead`** — concrete alternative-route claims to verify |
| Revenue/margin/cashflow | Only rival benchmarks (三花 28.77% GM); 英维克 liquid-cooling revenue still not separately disclosed | **`unknown`** — unchanged, correctly not estimated |
| Customer validation / share | 申菱 claims "头部客户认可/长期粘性" (unverified broker text) | `unknown` → `lead` (qualitative only) |
| Overseas competition | 申菱北美 2.5亿 new orders H1'25 (broker claim); no direct 英维克-vs-overseas benchmark yet | `unknown` → `lead` |

## 2. 北方华创 — semiconductor deposition/epitaxy

| Dimension | New lead evidence | Status |
|---|---|---|
| Node competition | 普达特科技 deep report (华鑫, 2026-04-10, p.24+): 清洗+LPCVD dual-drive — an alternate domestic supplier at 北方华创's own nodes; CMP + 薄膜沉积 industry reports (9 page-located extracts, batch-3) | `unknown` → **`lead`** for "who else competes at the node" |
| Overseas peer map | Ratings tables inside corpus (中微 688012, TSM/华虹/中芯 targets) give sell-side framing only | `unknown` → `lead` |
| Share / qualification depth | No report quantifies 北方华创 per-node installed share or per-process win rates | **`unknown`** — primary filings still required |
| Revenue/margin/cashflow per product line | Not separately disclosed in available corpus | **`unknown`** |

## 3. Method & integrity notes

- Every new extract carries `page_locator` + `unverified_research_lead` status; nothing was
  promoted to claim/`verified`. Six node auto-associations exist from staging; all other
  node mappings await human review.
- Corpus provenance: `theme_source_page_evidence_preview.csv` (56 extracts, batch-3 20-report set)
  and `..._remaining47.csv` (92 extracts, batch-4 47-report set) under
  `outputs/research/theme_research_yanbaoke_*20261019/`.
- Counter-evidence retained: pilot's negative-control (humanoid) stays `draft`/`unknown`;
  the liquid-cooling corpus itself is the counter-evidence pool for "英维克 uniqueness"
  (multiple credible domestic rivals named).
- No mapping, claim, or dossier row was written to the production theme DB.

## 4. Next deepening steps (need human/node-review decisions)

1. Node mapping review of the 20+47 gated source batches (6 auto-matched + rest manual).
2. Pull 英维克/北方华创 primary filings (annual/interim) for the still-`unknown`
   revenue-share/GM/cashflow dimensions — the corpus cannot fill these.
3. Cross-check the NVIDIA-Kyber/Google-CDU 屏蔽泵 claims against primary sources before
   any claim-state upgrade — currently single-broker assertions.
