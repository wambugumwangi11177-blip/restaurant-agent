# ADR 0003 — Postgres full-text search before vector search

**Status:** Accepted, 2026-09-26

## Context
The first plan draft said "embed into pgvector" but named no embedding provider. The configured chat providers (OpenRouter, Anthropic, Groq) aren't wired for embeddings in this stack, and Anthropic offers no embedding model.

## Decision
- Retrieval sits behind a `Retriever` protocol. The first implementation is Postgres full-text search: a generated `tsvector` column with headings weighted above body text, a GIN index, and `ts_rank_cd` ranking.
- Queries are OR-matched on their own stemmed lexemes, so natural-language questions work. Each lexeme is quoted, so punctuation can't break the query syntax.
- Every hit is a citation: document, chunk, heading path and a highlighted snippet.
- Quality is measured by the retrieval eval (`evals/retrieval/`) and gated in CI.

## Consequences
- Free, deterministic, no new key, and exactly testable.
- Weak on synonyms and paraphrase. When the eval shows misses that are paraphrase problems, add a `VectorRetriever` or hybrid retriever once an embedding provider is chosen. That is a founder decision (cost and data sharing). Callers don't change.
