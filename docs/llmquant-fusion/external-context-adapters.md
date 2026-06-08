# External Context Adapter Design

This design defines how future LLMQuant Data / MCP usage can enter `stock_research` without bypassing local storage, point-in-time review, or evidence contracts.

## Allowed External Context

Phase one allows only supplemental context:

- FRED macro series
- SEC filings
- 13F holdings
- external paper search
- external wiki or reference search

These sources can support analyst context, market regime notes, peer/reference research, or hypothesis generation. They are not primary A-share evidence.

## Blocked Categories

Phase one blocks:

- A-share prices
- A-share finance rows
- A-share factor scores
- trade signals
- broker, order, account, cash, position, fill, or execution data

These categories must remain controlled by the local PostgreSQL data model, local pipelines, local validation, and human review.

## Adapter Output Shape

Every external context adapter must emit a JSON-serializable artifact with:

- `source`: external provider or MCP name
- `query`: exact query or request descriptor
- `retrieved_at`: timestamp when the external payload was fetched
- `available_at`: timestamp or date when the underlying information became available
- `payload_path`: local stored raw or normalized payload artifact path
- `summary`: short local summary
- `evidence_units`: local `EvidenceUnit` dictionaries derived from the payload
- `warnings`: retrieval, coverage, freshness, or licensing warnings

## Artifact-First Rule

External payloads must be stored as local artifacts before they can appear in:

- daily report bundles
- watchlist memos
- risk or position review outputs
- `AgentObservation.evidence`
- report delivery manifests

External context must be labelled as `external_context`. It must not be labelled as primary A-share market, finance, factor, score, or watchlist evidence.

## Review Boundary

External context can suggest follow-up questions and provide background. It cannot:

- replace local A-share PIT data
- override factor scores or watchlist rules
- produce direct trading instructions
- mutate dashboard, watchlist, account, broker, cash, position, or execution state
