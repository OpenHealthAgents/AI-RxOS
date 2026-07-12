# Bounded Contexts - AI-RxOS

## Overview
AI-RxOS is organized into 12 bounded contexts based on Domain-Driven Design principles. Each context has clear boundaries, owns its data, and exposes well-defined APIs.

---

## 1. Identity & Access Context
**Purpose:** Authentication, authorization, and user management

**Core Concepts:**
- User
- Role
- Permission
- Organization
- Workspace
- Project
- API Key
- Session
- Audit Log

**Responsibilities:**
- User authentication (OAuth2, OIDC, SAML, Passkeys)
- Role-based access control (RBAC)
- Attribute-based access control (ABAC)
- Multi-tenant isolation (Organization → Workspace → Project)
- API key management
- Session management
- Audit logging
- Compliance monitoring

**Ubiquitous Language:**
- Tenant: Organization or workspace with isolated data
- Principal: Authenticated user or service account
- Grant: Permission to perform an action on a resource
- Policy: Rule governing access decisions

---

## 2. Knowledge Graph Context
**Purpose:** Biomedical knowledge representation and reasoning

**Core Concepts:**
- Entity (Gene, Protein, Disease, Drug, Target, Company, etc.)
- Relationship (Targets, Treats, Interacts, etc.)
- Ontology
- Evidence
- Graph Version
- Graph Query
- Graph Traversal

**Responsibilities:**
- Entity resolution and deduplication
- Relationship extraction
- Ontology mapping (GO, MeSH, ChEBI, etc.)
- Graph versioning
- Evidence scoring
- Graph querying (Cypher, Gremlin)
- Graph visualization
- Temporal graph operations

**Ubiquitous Language:**
- Node: Graph entity with properties
- Edge: Typed relationship between nodes
- Evidence: Source citation supporting a relationship
- Confidence: Score indicating relationship strength
- Provenance: Origin of graph data

---

## 3. Literature Intelligence Context
**Purpose:** Automated ingestion and analysis of scientific literature

**Core Concepts:**
- Publication
- Source (PubMed, bioRxiv, Conference, Patent)
- Ingestion Pipeline
- Extracted Entity
- Summary
- Citation Network
- Novelty Score
- Duplicate Detection

**Responsibilities:**
- Ingest from PubMed, PMC, bioRxiv, medRxiv, conferences, patents
- Automatic summarization
- Entity extraction (NER)
- Knowledge graph generation
- Duplicate detection
- Scientific novelty scoring
- Evidence ranking
- Citation linking
- Full-text indexing

**Ubiquitous Language:**
- Source: External data provider
- Ingestion: Process of acquiring and processing documents
- Extraction: Identification of structured entities from text
- Novelty: Measure of new scientific contribution
- Canonical ID: Persistent identifier for deduplication

---

## 4. AI Orchestration Context
**Purpose:** AI agent coordination and model management

**Core Concepts:**
- Agent
- Tool
- Model
- Prompt
- Context
- Conversation
- Workflow
- Tool Call
- Model Inference

**Responsibilities:**
- Agent lifecycle management
- Tool registry and execution
- Model registry and versioning
- Prompt template management
- Context window management
- Conversation memory
- Workflow orchestration (LangGraph, Temporal)
- Model Context Protocol (MCP) implementation
- Multi-agent coordination

**Ubiquitous Language:**
- Agent: Autonomous AI entity with tools and goals
- Tool: Function or API an agent can call
- Model: AI foundation model (LLM, embedding, etc.)
- Context: Information available to an agent
- Turn: Single interaction in a conversation
- Workflow: Multi-step agent process

---

## 5. Scientific Search Context
**Purpose:** Semantic search and retrieval across biomedical content

**Core Concepts:**
- Query
- Index
- Document
- Embedding
- Vector
- Hybrid Search
- Semantic Similarity
- Citation Graph
- Ranking

**Responsibilities:**
- Keyword search (OpenSearch/Elasticsearch)
- Vector search (pgvector, specialized vector DB)
- Hybrid search (keyword + vector)
- Graph search (Neo4j)
- Citation search
- Evidence search
- Re-ranking
- Query expansion
- Faceted search

**Ubiquitous Language:**
- Index: Searchable collection of documents
- Embedding: Vector representation of text
- Hybrid: Combination of search methods
- Relevance: Match quality between query and result
- Facet: Filterable category

---

## 6. Molecule Discovery Context
**Purpose:** Computational chemistry and molecular design

**Core Concepts:**
- Molecule
- Target
- Protein Structure
- Binding Pocket
- Docking
- ADMET
- Pharmacokinetics
- Toxicity
- Synthetic Accessibility
- Patent Similarity

**Responsibilities:**
- Virtual screening
- Generative chemistry
- Molecular docking
- ADMET prediction
- BBB penetration prediction
- PK prediction
- Toxicity prediction
- Synthetic accessibility scoring
- Patent similarity analysis
- Molecular property calculation

**Ubiquitous Language:**
- SMILES: String representation of molecular structure
- Docking: Computational prediction of ligand binding
- ADMET: Absorption, Distribution, Metabolism, Excretion, Toxicity
- BBB: Blood-brain barrier
- SA: Synthetic accessibility

---

## 7. Clinical Intelligence Context
**Purpose:** Clinical trial analysis and prediction

**Core Concepts:**
- Clinical Trial
- Phase
- Indication
- Endpoint
- Biomarker
- Patient Population
- Success Probability
- Trial Outcome
- Comparator

**Responsibilities:**
- Clinical trial ingestion
- Phase success prediction
- Indication expansion analysis
- Biomarker identification
- Companion diagnostic recommendation
- Combination therapy analysis
- Competitive trial tracking
- Trial outcome prediction

**Ubiquitous Language:**
- IND: Investigational New Drug application
- NDA: New Drug Application
- Endpoint: Measured outcome in a trial
- Biomarker: Biological indicator of disease or response
- Comparator: Standard of care or placebo

---

## 8. Competitive Intelligence Context
**Purpose:** Market and competitor analysis

**Core Concepts:**
- Competitor
- Pipeline
- Asset
- Market Map
- Technology Landscape
- Funding Round
- Leadership Change
- Licensing Opportunity
- Threat Analysis

**Responsibilities:**
- Competitor tracking
- Pipeline monitoring
- Conference presentation tracking
- Patent monitoring
- Company announcement tracking
- Funding round tracking
- Market map generation
- Technology landscape analysis
- Threat analysis
- Licensing opportunity identification

**Ubiquitous Language:**
- Asset: Drug or therapeutic in development
- Pipeline: Collection of assets in development
- FIC: First-in-class
- BIC: Best-in-class
- MoA: Mechanism of Action

---

## 9. Portfolio Management Context
**Purpose:** Portfolio evaluation and optimization

**Core Concepts:**
- Portfolio
- Asset
- Score
- Risk
- ROI
- Probability of Success
- Commercial Opportunity
- Scientific Novelty
- Patent Strength
- Investment Recommendation

**Responsibilities:**
- Portfolio scoring
- Scientific novelty assessment
- Commercial opportunity evaluation
- Competitive positioning analysis
- Patent landscape analysis
- Development cost estimation
- Probability of success calculation
- Investment recommendation
- Priority ranking

**Ubiquitous Language:**
- PoS: Probability of Success
- NPV: Net Present Value
- Risk-adjusted return: Return adjusted for failure probability
- Commercial score: Market potential assessment
- Technical score: Scientific feasibility assessment

---

## 10. Collaboration Context
**Purpose:** Scientific collaboration and document management

**Core Concepts:**
- Notebook
- Document
- Comment
- Version
- Citation
- Reference
- Dashboard
- Report
- Template

**Responsibilities:**
- Scientific notebook management
- Document versioning
- Real-time collaboration
- Citation management
- Reference linking
- Dashboard creation
- Report generation
- Template management
- Export (PDF, DOCX, PPTX)

**Ubiquitous Language:**
- Notebook: Interactive scientific document
- Cell: Unit of content in a notebook
- Citation: Reference to a publication
- Version: Immutable snapshot of a document
- Fork: Copy of a document for independent editing

---

## 11. Data Integration Context
**Purpose:** External data source integration

**Core Concepts:**
- Data Source
- Connector
- Ingestion Job
- Transformation
- Validation
- Schema Mapping
- Data Quality
- Sync Schedule

**Responsibilities:**
- Connector management (PubMed, ChEMBL, DrugBank, etc.)
- Ingestion scheduling
- Data transformation
- Schema mapping
- Data validation
- Error handling
- Retry logic
- Data quality monitoring

**Ubiquitous Language:**
- Connector: Interface to external data source
- Ingestion: Process of acquiring external data
- Transformation: Conversion of data to internal format
- Validation: Verification of data quality
- Sync: Scheduled data refresh

---

## 12. Observability Context
**Purpose:** System monitoring and analytics

**Core Concepts:**
- Metric
- Log
- Trace
- Alert
- Dashboard
- Health Check
- SLO
- SLA
- AI Metric

**Responsibilities:**
- Centralized logging
- Metrics collection
- Distributed tracing
- Health checks
- Alerting
- AI inference metrics
- GPU utilization monitoring
- Model drift detection
- Prompt analytics
- User analytics

**Ubiquitous Language:**
- Metric: Quantitative measurement
- Trace: Request path through system
- Span: Single unit of work in a trace
- SLO: Service Level Objective
- SLA: Service Level Agreement
- Drift: Model performance degradation over time

---

## Context Mapping

### Upstream Dependencies
- **Data Integration** → All contexts (provides raw data)
- **Identity & Access** → All contexts (provides auth/authz)
- **Literature Intelligence** → Knowledge Graph (provides extracted entities)
- **Knowledge Graph** → Scientific Search, AI Orchestration (provides graph data)

### Downstream Dependencies
- **AI Orchestration** → All contexts (consumes data via agents)
- **Scientific Search** → All contexts (provides search capabilities)
- **Collaboration** → All contexts (provides document management)

### Anti-Corruption Layers
- **Data Integration**: ACL for each external source
- **Literature Intelligence**: ACL for unstructured text processing
- **Clinical Intelligence**: ACL for clinical trial data formats

### Shared Kernel
- **Common Domain**: IDs, timestamps, audit fields
- **Domain Events**: Standardized event format
- **API Contracts**: OpenAPI specifications

---

## Context Relationships

```
┌─────────────────────────────────────────────────────────────┐
│                    Identity & Access                        │
│                  (Upstream to all contexts)                 │
└─────────────────────────────────────────────────────────────┘
                              │
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                     Data Integration                        │
│                  (Upstream to all contexts)                 │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ↓               ↓               ↓
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│ Literature       │ │ Knowledge Graph  │ │ Clinical         │
│ Intelligence     │ │                  │ │ Intelligence     │
└──────────────────┘ └──────────────────┘ └──────────────────┘
              │               │               │
              └───────────────┼───────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                   AI Orchestration                          │
│              (Coordinates all contexts)                     │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ↓               ↓               ↓
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│ Scientific       │ │ Molecule         │ │ Competitive      │
│ Search           │ │ Discovery        │ │ Intelligence     │
└──────────────────┘ └──────────────────┘ └──────────────────┘
                              │
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                   Portfolio Management                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    Collaboration                            │
│              (Downstream to all contexts)                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                    Observability                            │
│              (Cross-cutting concern)                        │
└─────────────────────────────────────────────────────────────┘
```
