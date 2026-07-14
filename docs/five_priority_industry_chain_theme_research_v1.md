# Five Priority Industry Chains in Theme Research

The Industry Catalog remains the structural directory. Five priority chains now open into full Theme Research packages:

- AI data-center power
- Semiconductor manufacturing equipment
- Humanoid robots and embodied intelligence
- AI compute infrastructure
- New energy storage

Each package contains a research conclusion, value flow, profit-pool and barrier assessment, catalysts and risks, validation signals, evidence-backed company mappings, source details, and explicit evidence gaps.

## How to Read It

1. Open `主题研究` and enter `产业目录` to understand the canonical L3/L4 structure.
2. On one of the five selected chains, click `进入深度研究`.
3. Start with `研究结论` and `价值链` to understand where products, services and operating economics connect.
4. Use `利润池与竞争壁垒` to distinguish product presence from durable value capture.
5. Read `催化、验证信号与风险` as a monitoring checklist rather than a forecast.
6. Filter `受益公司` by beneficiary tier and open the mapping evidence before using a company in further research.
7. Use `来源证据` and `证据缺口与更新` to see what is verified and what remains unknown.

## Beneficiary Tiers

- `core_beneficiary`: reviewed direct relationship, strong bottleneck relevance, and disclosed business materiality.
- `elastic_beneficiary`: reviewed direct relationship, but the theme-specific revenue or materiality remains emerging or undisclosed.
- `indirect_beneficiary`: reviewed adjacent supplier, system integrator, or downstream operator relationship.
- `concept_association`: insufficient direct accepted evidence, draft mapping, reserve-stage activity, or concept-only exposure.

The current packages deliberately use conservative tiers. A company is not promoted because it appears in a media or social supply-chain list.

## Evidence Standard

Reviewed company mappings require an accepted S0/S1 source and excerpt-level product, service, or customer relationship evidence. Claims of core or material revenue additionally require revenue-materiality evidence. Company filings support relevance; they do not prove future orders, margin expansion, valuation, or investment return.

## Completion Gate

Run:

```bash
rtk env PYTHONPATH=src:. .venv/bin/python scripts/verify_five_industry_chain_themes.py --format markdown
```

Every selected theme must have a catalog link, all theme nodes accounted for, L3 and L4 linkage, at least ten accepted sources, at least four primary/first-party sources, ten structured claims, and at least eight reviewed evidence-backed company mappings.

All outputs are research-only and are not used for signals, admissions, automated review decisions, or database writes.
