# Midtrend Post-Exit Fundamental Attribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a research-only diagnostic package that explains which Mid Trend exits continue, which fail, and how technical/mainline/fundamental fields separate them.

**Architecture:** Reuse existing baseline top5, accepted top10 candidate, and prior sweep/re-entry artifacts as static inputs. Build one diagnostic runner that constructs a unified post-exit observation pool, computes forward path behavior, joins available as-of technical/mainline/fundamental fields, and emits attribution tables without changing any trading logic.

**Tech Stack:** Python, pandas, existing `stock_research` artifact readers and Mid Trend helper outputs, pytest

---
