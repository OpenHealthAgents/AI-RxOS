# AI-RxOS AI System Baseline

## Current Runtime

The substantive reusable AI runtime is `services/agents`. It provides a custom
bounded graph runtime, checkpointing, Redis Stream jobs, retries,
idempotency, prompt/model/tool registries, MCP integration, memory, streaming,
redaction, and provider adapters. Its deterministic suite is documented in
`services/agents/TESTING.md`.

`apps/ai-services` is a separate facade/stub and is not the full production
runtime. The architecture references to the OpenAI Agents SDK and external
LangGraph are not current implementation facts.

## Evidence Boundary

AI components may retrieve and summarize cited evidence, propose observations,
calculate derived features, produce hypotheses/rankings/recommendations with
uncertainty, and route work to human reviewers.

AI components must not invent evidence or citations, turn inference into fact,
make definitive legal/licensing/FTO conclusions, overwrite source observations,
or bypass tenant authorization and audit requirements.

## Future Domain Agents

Target discovery, literature, patent, conference, molecule, docking,
medicinal-chemistry, safety/ADMET, biomarker, resistance, combination,
commercial, licensing, and IP agents are planned domain implementations. The
generic runtime is reusable infrastructure, not proof these agents exist.

## Evaluation Requirements

Every intelligence engine must define its evidence and temporal cutoff, output
schema, uncertainty, provenance, model/prompt/tool version, contradiction
handling, leakage tests, human override behavior, deterministic tests, and
representative fixtures.