# Midtrend Top10 Candidate And Reentry Gating Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Promote clean top10 Mid Trend into the next candidate baseline and separately test narrow re-entry left-tail gating without touching the original v1 baseline.

**Architecture:** Add one standalone top10 strategy wrapper that reuses the existing v1 regime/protection logic with `top_n=10`, and add one dedicated gating experiment runner that reuses the strict re-entry engine with parameterized gating knobs. Keep baseline immutable, keep default re-entry behavior backward-compatible, and produce comparison artifacts in isolated output directories.

**Tech Stack:** Python, pandas, existing `stock_research` strategy/backtest helpers, pytest

---
