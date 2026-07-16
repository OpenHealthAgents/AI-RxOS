Given the scope of AI-RxOS, I would not ask an AI coding agent to build the whole platform in one prompt. Most coding agents (Codex, Claude Code, Gemini CLI, Cursor Agent, Windsurf, etc.) perform much better when working from a clear architecture and a sequence of narrowly scoped milestones.
I recommend treating the AI coding agent as a senior engineering team that receives a series of implementation epics rather than isolated coding tasks.
## Development methodology
Instead of this:
```
Build an AI Drug Discovery platform.
Use a progression like this:
```
```
Vision
↓

Architecture

↓

Repository

↓

Infrastructure

↓

Authentication

↓

Core Platform

↓

Knowledge Graph

↓

AI Platform

↓

Scientific Modules

↓

Enterprise Features

↓

Production
Each prompt should produce a complete, testable increment before moving to the next.
```

# Prompt 1 — Become the Lead Architect
```
You are the Lead Software Architect responsible for designing an enterprise AI-native Drug Discovery Operating System (AI-RxOS).

Your responsibilities include:

- Enterprise Architecture
- Domain Driven Design
- Microservices
- AI Agent Systems
- Scientific Computing
- Cloud Native Design
- Security
- Scalability

Before writing code:

1. Define the bounded contexts.
2. Define all services.
3. Define APIs.
4. Define databases.
5. Define event flows.
6. Define AI agent architecture.
7. Define deployment architecture.
8. Produce C4 diagrams.
9. Produce ER diagrams.
10. Produce sequence diagrams.

Do not generate code until the architecture is complete.

```
# Prompt 2 — Repository Setup
```
Create a production-ready monorepo.

Requirements

- Turborepo
- pnpm
- Next.js
- FastAPI
- Go API Gateway
- PostgreSQL
- Neo4j
- LLM Wiki (OKF)
- Redis
- OpenSearch
- Docker
- Kubernetes
- Helm

Repository

/apps
/web
/admin
/api-gateway
/ai-services
/knowledge-service

/packages
/ui
/sdk
/types
/config

/services
/auth
/literature
/kg
/search
/agents
/workflows
/reports
/docking

Deployable immediately.

```
# Prompt 3 — Authentication
```
Build enterprise authentication.

Requirements

Better Auth (with Org, Admin, and API-Key plugins)

OIDC

OAuth2

SSO

MFA

Passkeys

RBAC & OIDC Federated Authentication

ABAC

JWT tokens (locally validated via JWKS)

Refresh Tokens

Session Management

Workspace Membership

Organization Support

User Invitations

Audit Logs

Generate database schema, APIs, frontend, tests and documentation.

```
# Prompt 4 — Design System
```
Build an enterprise design system.

Use

Next.js

Tailwind

shadcn/ui

Create reusable components.

Dashboard

Data Tables

Graph Viewer

Knowledge Cards

Scientific Paper Viewer

Drug Cards

Timeline

Notebook

Chat Interface

Docking Viewer

Charts

Responsive.

Dark mode.

Accessibility.

Storybook included.

```
# Prompt 5 — Knowledge Graph
```
Build the biomedical knowledge graph service.

Neo4j

Nodes

Gene

Protein

Disease

Drug

Target

Mutation

Publication

Patent

Clinical Trial

Company

Conference

Relationships

Treats

Targets

Interacts

PresentedAt

PublishedIn

OwnedBy

CompetesWith

Generate

Graph APIs

Cypher Queries

Bulk Import

Versioning

Evidence Scoring

Tests.

```
# Prompt 6 — Literature Intelligence
```
Build the Literature Intelligence Service.

Sources

PubMed

PMC

ClinicalTrials.gov

bioRxiv

AACR

ASCO

SABCS

ESMO

Company Press Releases

Pipeline

Crawler

Parser

NER

Summarizer

Entity Extraction

Relationship Extraction

Knowledge Graph Update

LLM Wiki Compilation

Duplicate Detection

Evidence Ranking

Generate production-ready services.

```
# Prompt 7 — LLM Wiki Search
```
Build hybrid search (qmd BM25 + local vector).

Use

OpenSearch

LLM Wiki (OKF)

BM25

Hybrid Ranking

Semantic Search

Citation Search

Graph Search

Streaming Results

Support

100 million documents.

Include benchmarks.

```
# Prompt 8 — AI Platform
```
Build the AI Platform.

Use

OpenAI Agents SDK

Model Context Protocol

Multi-agent orchestration

Conversation Memory

Prompt Registry

Tool Registry

Model Registry

RAG

Streaming

Observability

Support multiple LLM providers.

Generate architecture and code.

```
# Prompt 9 — AI Scientist
```
Create AI Scientist agents.

Target Discovery

Literature Review

Patent Review

Conference Analysis

Drug Discovery

Medicinal Chemistry

Clinical Trial Analysis

Competitive Intelligence

Portfolio Builder

Scientific Writer

Each agent

Tools

Memory

Planning

Reasoning

Structured Outputs

Evaluation Tests.

```
# Prompt 10 — Scientific Workspace
```
Build scientific workspaces.

Projects

Datasets

Notebooks

Experiments

Documents

References

Tasks

Version Control

Collaboration

Comments

Permissions

Activity Timeline.

```
# Prompt 11 — Molecule Discovery
```
Build Molecule Discovery.

Input

SMILES

Protein

PDB

Target

Generate

Docking

ADMET

BBB

PK

Toxicity

Synthetic Accessibility

Novelty

Patent Similarity

Use

RDKit

ESM

BioNeMo

PyTorch

Provide APIs.

```
# Prompt 12 — Competitive Intelligence
```
Build Competitive Intelligence.

Track

Companies

Pipelines

Clinical Trials

Publications

Patents

Funding

Conference Presentations

Generate

Dashboards

Alerts

Comparison Tables

Threat Scores

Opportunity Scores.

```
# Prompt 13 — Portfolio Builder
```
Create Portfolio Builder.

Score

Scientific Novelty

Commercial Opportunity

Competition

Patent Position

Clinical Risk

Probability of Success

NPV

Generate

Prioritization Dashboard

Roadmaps

Investment Recommendations.

```
# Prompt 14 — Due Diligence
```
Build Due Diligence.

User uploads

Pitch Deck

Patent

Scientific Paper

Company Deck

Generate

Strengths

Weaknesses

Competitive Landscape

Patent Risks

Scientific Risks

Commercial Risks

Executive Report.

```
# Prompt 15 — Observability
```
Add enterprise observability.

OpenTelemetry

Prometheus

Grafana

Jaeger

Structured Logging

GPU Monitoring

LLM Metrics

Prompt Analytics

Latency

Cost Tracking.

```
# Prompt 16 — Security
```
Implement enterprise security.

SOC2

HIPAA-ready architecture

Encryption

Secrets

Vault

Audit

Immutable Logs

Rate Limiting

Threat Detection

Security Headers

Pen Testing.

```
# Prompt 17 — Kubernetes
```
Deploy to Kubernetes.

Generate

Dockerfiles

Helm

Terraform

AKS

Ingress

Autoscaling

GPU Nodes

CI/CD

Blue Green

Canary

Secrets

Monitoring.

```
# Prompt 18 — Production Hardening
```
Review the entire platform.

Refactor.

Remove duplicate code.

Improve performance.

Improve scalability.

Improve developer experience.

Improve testing.

Achieve production readiness.

```
# Phase 2: Scientific AI prompts
Once the core platform is complete, shift the coding agent toward domain-specific capabilities:
- Build a biomedical ontology and knowledge graph aligned with ChEMBL, DrugBank, Open Targets, UniProt, PDB, and HGNC.
- Implement ingestion pipelines for PubMed, PubMed Central, ClinicalTrials.gov, conference abstracts (AACR, ASCO, SABCS), patents, and company press releases.
- Create AI workflows for target discovery, mechanism-of-action analysis, biomarker identification, and competitive landscape assessment.
- Integrate molecular design tools (RDKit, BioNeMo, ESM, AlphaFold-derived structures) with docking and ADMET prediction.
- Develop evaluation frameworks so every AI agent is measured on citation quality, reasoning accuracy, reproducibility, and latency.
## A recommendation that will significantly improve results
Don't let the coding agent write code immediately. Have it act in three distinct modes for every major feature:
- Architect Mode – Produce architecture, ADRs, API contracts, ER diagrams, sequence diagrams, and acceptance criteria.
- Implementation Mode – Generate production-quality code, tests, migrations, infrastructure, and documentation.
- Reviewer Mode – Perform a rigorous code review, identify security and scalability issues, propose refactors, and only then approve the feature.
This architecture → implementation → review cycle typically yields much more maintainable results than asking an AI agent to code features directly. It also mirrors how experienced engineering teams deliver complex enterprise software and will make AI-RxOS easier to extend as you add additional scientific capabilities.
