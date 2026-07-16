# ER Diagrams - AI-RxOS

## Overview
This document contains Entity-Relationship (ER) diagrams for all databases in AI-RxOS: PostgreSQL, Neo4j, and Redis data structures.

---

## 1. PostgreSQL ER Diagrams

### 1.1 Identity & Access Schema

```mermaid
erDiagram
    user ||--o{ account : "has"
    user ||--o{ session : "has"
    user ||--o{ user_role : "has"
    user ||--o{ member : "member of"
    user ||--o{ workspace_member : "member of"
    user ||--o{ project_member : "member of"
    user ||--o{ api_key : "owns"
    user ||--o{ audit_log : "performs"
    
    role ||--o{ user_role : "assigned in"
    
    organization ||--o{ member : "has members"
    organization ||--o{ workspace : "contains"
    
    workspace ||--o{ workspace_member : "has members"
    workspace ||--o{ project : "contains"
    
    project ||--o{ project_member : "has members"
    
    user {
        uuid id PK
        varchar email UK
        boolean email_verified
        varchar name
        varchar avatar_url
        timestamp created_at
        timestamp updated_at
    }
    
    account {
        uuid id PK
        varchar account_id
        varchar provider_id
        uuid user_id FK
        text access_token
        text refresh_token
        text id_token
        timestamp expires_at
        text password
    }
    
    session {
        uuid id PK
        uuid user_id FK
        timestamp expires_at
        varchar ip_address
        varchar user_agent
        timestamp created_at
        timestamp updated_at
    }
    
    verification {
        uuid id PK
        varchar identifier
        varchar value
        timestamp expires_at
        timestamp created_at
    }
    
    organization {
        uuid id PK
        varchar name
        varchar slug UK
        varchar logo_url
        varchar plan
        integer max_users
        integer max_workspaces
        jsonb settings
        timestamp created_at
        timestamp updated_at
        timestamp deleted_at
    }
    
    member {
        uuid id PK
        uuid organization_id FK
        uuid user_id FK
        varchar role
        timestamp created_at
        timestamp updated_at
    }
    
    role {
        uuid id PK
        varchar name UK
        text description
        jsonb permissions
        timestamp created_at
        timestamp updated_at
    }
    
    user_role {
        uuid id PK
        uuid user_id FK
        uuid role_id FK
        uuid organization_id FK
        uuid workspace_id
        uuid project_id
        uuid granted_by FK
        timestamp granted_at
        timestamp expires_at
    }
    
    workspace {
        uuid id PK
        uuid organization_id FK
        varchar name
        text description
        jsonb settings
        timestamp created_at
        timestamp updated_at
        timestamp deleted_at
    }
    
    workspace_member {
        uuid id PK
        uuid workspace_id FK
        uuid user_id FK
        varchar role
        timestamp joined_at
    }
    
    project {
        uuid id PK
        uuid workspace_id FK
        varchar name
        text description
        varchar status
        jsonb settings
        timestamp created_at
        timestamp updated_at
        timestamp deleted_at
    }
    
    project_member {
        uuid id PK
        uuid project_id FK
        uuid user_id FK
        varchar role
        timestamp joined_at
    }
    
    api_key {
        uuid id PK
        uuid user_id FK
        uuid organization_id FK
        uuid workspace_id FK
        varchar name
        varchar key_hash UK
        varchar prefix
        text[] scopes
        timestamp expires_at
        timestamp last_used_at
        timestamp created_at
        timestamp revoked_at
    }
    
    audit_log {
        uuid id PK
        uuid user_id FK
        uuid organization_id FK
        uuid workspace_id FK
        uuid project_id FK
        varchar action
        varchar resource_type
        uuid resource_id
        varchar ip_address
        varchar user_agent
        jsonb metadata
        timestamp created_at
    }
```

---

### 1.2 Knowledge Graph Schema

```mermaid
erDiagram
    graph_nodes ||--o{ graph_relationships : "from"
    graph_nodes ||--o{ graph_relationships : "to"
    graph_nodes ||--o{ entity_mappings : "canonical"
    
    ontologies ||--o{ ontology_terms : "contains"
    
    graph_nodes {
        uuid id PK
        varchar graph_id UK
        varchar type
        text[] labels
        jsonb properties
        float confidence
        jsonb provenance
        integer version
        timestamp created_at
        timestamp updated_at
        timestamp deleted_at
    }
    
    graph_relationships {
        uuid id PK
        uuid from_node_id FK
        uuid to_node_id FK
        varchar type
        jsonb properties
        float confidence
        jsonb evidence
        jsonb provenance
        integer version
        timestamp created_at
        timestamp updated_at
        timestamp deleted_at
    }
    
    entity_mappings {
        uuid id PK
        uuid canonical_id FK
        varchar alias_id
        varchar source
        float confidence
        timestamp created_at
    }
    
    ontologies {
        uuid id PK
        varchar name UK
        varchar version
        varchar source_url
        text description
        varchar format
        varchar file_path
        timestamp imported_at
        timestamp updated_at
    }
    
    ontology_terms {
        uuid id PK
        uuid ontology_id FK
        varchar term_id
        varchar name
        text definition
        text[] parent_ids
        text[] synonyms
        jsonb properties
    }
```

---

### 1.3 Literature Intelligence Schema

```mermaid
erDiagram
    ingestion_sources ||--o{ ingestion_jobs : "creates"
    ingestion_jobs ||--o{ documents : "produces"
    
    documents ||--o{ extracted_entities : "contains"
    documents ||--o{ extracted_relationships : "contains"
    documents ||--o{ document_summaries : "has"
    documents ||--o{ duplicate_group_members : "member of"
    documents ||--o{ novelty_scores : "has"
    
    duplicate_groups ||--o{ duplicate_group_members : "has members"
    
    extracted_entities ||--o{ extracted_relationships : "from"
    extracted_entities ||--o{ extracted_relationships : "to"
    
    ingestion_sources {
        uuid id PK
        varchar name
        varchar type
        jsonb config
        boolean enabled
        timestamp last_sync_at
        varchar sync_schedule
        timestamp created_at
        timestamp updated_at
    }
    
    ingestion_jobs {
        uuid id PK
        uuid source_id FK
        varchar status
        text query
        jsonb parameters
        timestamp started_at
        timestamp completed_at
        integer documents_processed
        integer documents_failed
        text error_message
        timestamp created_at
    }
    
    documents {
        uuid id PK
        uuid source_id FK
        varchar source_document_id UK
        text title
        text abstract
        text full_text
        text[] authors
        date publication_date
        varchar journal
        varchar doi
        varchar pmid
        varchar pmcid
        varchar url
        varchar document_type
        varchar language
        jsonb metadata
        timestamp indexed_at
        timestamp created_at
        timestamp updated_at
    }
    
    extracted_entities {
        uuid id PK
        uuid document_id FK
        varchar entity_type
        varchar entity_text
        uuid canonical_id FK
        float confidence
        integer start_position
        integer end_position
        varchar extraction_model
        timestamp extracted_at
    }
    
    extracted_relationships {
        uuid id PK
        uuid document_id FK
        uuid from_entity_id FK
        uuid to_entity_id FK
        varchar relationship_type
        float confidence
        text evidence
        varchar extraction_model
        timestamp extracted_at
    }
    
    document_summaries {
        uuid id PK
        uuid document_id FK
        text summary
        text[] key_points
        varchar summary_model
        float confidence
        timestamp created_at
    }
    
    duplicate_groups {
        uuid id PK
        uuid representative_document_id FK
        float similarity_threshold
        timestamp created_at
    }
    
    duplicate_group_members {
        uuid group_id FK
        uuid document_id FK
        float similarity
    }
    
    novelty_scores {
        uuid id PK
        uuid document_id FK
        float novelty_score
        jsonb aspects
        varchar scoring_model
        timestamp scored_at
    }
```

---

### 1.4 AI Orchestration Schema

```mermaid
erDiagram
    agents ||--o{ conversations : "handles"
    models ||--o{ model_versions : "has versions"
    model_versions ||--o{ model_evaluations : "evaluated by"
    
    prompts ||--o{ prompt_versions : "has versions"
    
    conversations ||--o{ messages : "contains"
    messages ||--o{ tool_calls : "contains"
    
    agents {
        uuid id PK
        varchar name
        varchar type
        text description
        jsonb config
        uuid model_id FK
        text system_prompt
        jsonb tools
        boolean enabled
        integer version
        uuid created_by FK
        timestamp created_at
        timestamp updated_at
    }
    
    conversations {
        uuid id PK
        uuid agent_id FK
        uuid user_id FK
        uuid workspace_id FK
        uuid project_id FK
        varchar title
        varchar status
        jsonb metadata
        timestamp created_at
        timestamp updated_at
    }
    
    messages {
        uuid id PK
        uuid conversation_id FK
        varchar role
        text content
        jsonb tool_calls
        jsonb metadata
        integer token_count
        timestamp created_at
    }
    
    tool_calls {
        uuid id PK
        uuid message_id FK
        varchar tool_id
        varchar tool_name
        jsonb parameters
        text result
        text error_message
        varchar status
        timestamp started_at
        timestamp completed_at
        timestamp created_at
    }
    
    models {
        uuid id PK
        varchar name
        varchar type
        varchar framework
        text description
        jsonb config
        varchar status
        timestamp created_at
        timestamp updated_at
    }
    
    model_versions {
        uuid id PK
        uuid model_id FK
        varchar version
        varchar artifact_uri
        jsonb config
        jsonb metrics
        boolean deployed
        jsonb deployment_config
        timestamp created_at
    }
    
    model_evaluations {
        uuid id PK
        uuid model_version_id FK
        varchar dataset_name
        jsonb metrics
        varchar evaluation_type
        timestamp created_at
    }
    
    prompts {
        uuid id PK
        varchar name
        text description
        text template
        jsonb variables
        integer version
        uuid created_by FK
        timestamp created_at
        timestamp updated_at
    }
    
    prompt_versions {
        uuid id PK
        uuid prompt_id FK
        integer version
        text template
        jsonb variables
        timestamp created_at
    }
    
    tools {
        uuid id PK
        varchar name UK
        text description
        varchar type
        jsonb config
        jsonb schema
        integer rate_limit
        boolean enabled
        timestamp created_at
        timestamp updated_at
    }
```

---

### 1.5 Molecule Discovery Schema

```mermaid
erDiagram
    molecules ||--o{ docking_jobs : "docked in"
    docking_jobs ||--o{ docking_results : "produces"
    molecules ||--o{ admet_predictions : "has"
    molecules ||--o{ generated_molecules : "generated as"
    
    molecules {
        uuid id PK
        varchar smiles
        varchar canonical_smiles UK
        varchar inchi
        varchar inchi_key
        varchar name
        varchar molecular_formula
        float molecular_weight
        jsonb properties
        timestamp created_at
        timestamp updated_at
    }
    
    docking_jobs {
        uuid id PK
        uuid target_id
        varchar ligand_smiles
        varchar protein_structure
        varchar status
        jsonb parameters
        timestamp started_at
        timestamp completed_at
        text error_message
        timestamp created_at
    }
    
    docking_results {
        uuid id PK
        uuid job_id FK
        integer pose_rank
        float score
        float rmsd
        jsonb pose_data
        jsonb interactions
        timestamp created_at
    }
    
    admet_predictions {
        uuid id PK
        uuid molecule_id FK
        varchar property_name
        float property_value
        varchar property_unit
        varchar prediction_class
        float confidence
        varchar model_version
        timestamp predicted_at
    }
    
    generated_molecules {
        uuid id PK
        uuid generation_job_id
        varchar smiles
        varchar canonical_smiles
        jsonb properties
        jsonb scores
        boolean selected
        timestamp created_at
    }
```

---

### 1.6 Clinical Intelligence Schema

```mermaid
erDiagram
    clinical_trials ||--o{ clinical_predictions : "predicted for"
    
    clinical_trials {
        uuid id PK
        varchar nct_id UK
        text title
        varchar phase
        varchar status
        varchar indication
        varchar sponsor
        date start_date
        date completion_date
        text primary_endpoint
        text[] secondary_endpoints
        text[] biomarkers
        integer enrollment
        jsonb locations
        varchar url
        jsonb metadata
        timestamp created_at
        timestamp updated_at
    }
    
    clinical_predictions {
        uuid id PK
        uuid trial_id FK
        uuid drug_id
        varchar indication
        varchar phase
        float success_probability
        float confidence
        jsonb factors
        varchar model_version
        timestamp predicted_at
    }
```

---

### 1.7 Competitive Intelligence Schema

```mermaid
erDiagram
    competitors ||--o{ competitor_assets : "owns"
    competitors ||--o{ competitor_events : "has events"
    
    competitors {
        uuid id PK
        varchar name
        varchar industry
        text[] focus_areas
        varchar website
        varchar funding_stage
        text description
        jsonb metadata
        timestamp created_at
        timestamp updated_at
    }
    
    competitor_assets {
        uuid id PK
        uuid competitor_id FK
        varchar name
        varchar type
        varchar indication
        varchar phase
        varchar mechanism
        varchar status
        jsonb metadata
        timestamp created_at
        timestamp updated_at
    }
    
    competitor_events {
        uuid id PK
        uuid competitor_id FK
        varchar event_type
        text title
        text description
        date event_date
        varchar source_url
        jsonb metadata
        timestamp created_at
    }
```

---

### 1.8 Portfolio Management Schema

```mermaid
erDiagram
    portfolios ||--o{ portfolio_assets : "contains"
    portfolio_assets ||--o{ asset_scores : "scored by"
    portfolios ||--o{ portfolio_scores : "has"
    
    portfolios {
        uuid id PK
        uuid workspace_id FK
        varchar name
        text description
        varchar status
        jsonb settings
        timestamp created_at
        timestamp updated_at
    }
    
    portfolio_assets {
        uuid id PK
        uuid portfolio_id FK
        varchar name
        varchar type
        varchar asset_type
        varchar indication
        varchar phase
        varchar mechanism
        varchar company
        jsonb metadata
        timestamp created_at
        timestamp updated_at
    }
    
    asset_scores {
        uuid id PK
        uuid asset_id FK
        varchar dimension
        float score
        float weight
        text explanation
        jsonb factors
        timestamp scored_at
    }
    
    portfolio_scores {
        uuid id PK
        uuid portfolio_id FK
        float composite_score
        float risk_score
        float roi_potential
        float diversification
        float balance
        timestamp scored_at
    }
```

---

### 1.9 Collaboration Schema

```mermaid
erDiagram
    notebooks ||--o{ notebook_cells : "contains"
    notebooks ||--o{ notebook_versions : "has versions"
    notebooks ||--o{ notebook_collaborators : "shared with"
    
    documents_v2 ||--o{ document_versions : "has versions"
    documents_v2 ||--o{ documents_v2 : "parent of"
    
    notebooks {
        uuid id PK
        uuid project_id FK
        varchar title
        text description
        uuid owner_id FK
        text[] tags
        jsonb settings
        timestamp created_at
        timestamp updated_at
        timestamp deleted_at
    }
    
    notebook_cells {
        uuid id PK
        uuid notebook_id FK
        varchar cell_type
        text content
        integer position
        jsonb metadata
        timestamp created_at
        timestamp updated_at
    }
    
    notebook_versions {
        uuid id PK
        uuid notebook_id FK
        integer version
        jsonb snapshot
        uuid created_by FK
        timestamp created_at
    }
    
    notebook_collaborators {
        uuid id PK
        uuid notebook_id FK
        uuid user_id FK
        varchar role
        timestamp joined_at
    }
    
    documents_v2 {
        uuid id PK
        uuid workspace_id FK
        uuid folder_id FK
        varchar name
        varchar type
        bigint size
        varchar file_path
        uuid owner_id FK
        jsonb metadata
        timestamp created_at
        timestamp updated_at
        timestamp deleted_at
    }
    
    document_versions {
        uuid id PK
        uuid document_id FK
        integer version
        varchar file_path
        bigint size
        uuid created_by FK
        timestamp created_at
    }
    
    reports {
        uuid id PK
        varchar name
        varchar type
        uuid template_id
        jsonb parameters
        varchar status
        varchar file_path
        uuid generated_by FK
        timestamp created_at
        timestamp completed_at
    }
```

---

### 1.10 Data Integration Schema

```mermaid
erDiagram
    connectors ||--o{ transformations : "has"
    
    connectors {
        uuid id PK
        varchar name
        varchar type
        jsonb config
        boolean enabled
        varchar health_status
        timestamp last_health_check
        timestamp created_at
        timestamp updated_at
    }
    
    transformations {
        uuid id PK
        uuid connector_id FK
        varchar name
        jsonb source_schema
        jsonb target_schema
        jsonb mapping_rules
        jsonb validation_rules
        boolean enabled
        timestamp created_at
        timestamp updated_at
    }
```

---

### 1.11 Observability Schema

```mermaid
erDiagram
    health_history {
        uuid id PK
        varchar service_name
        varchar status
        integer latency_ms
        text error_message
        jsonb metadata
        timestamp checked_at
    }
```

---

## 2. Neo4j Graph Schema

### 2.1 Graph Node Types

```mermaid
erDiagram
    Gene ||--o{ Protein : "encodes"
    Protein ||--o{ Drug : "targets"
    Drug ||--o{ Disease : "treats"
    Disease ||--o{ ClinicalTrial : "trial for"
    Company ||--o{ Drug : "develops"
    Company ||--o{ Patent : "owns"
    Publication ||--o{ Patent : "cites"
    Conference ||--o{ Publication : "presents"
    Biomarker ||--o{ Disease : "biomarker for"
    Pathway ||--o{ Protein : "contains"
    Mutation ||--o{ Gene : "mutation of"
    
    Gene {
        string id PK
        string canonical_id UK
        string name
        string symbol
        string entrez_id
        string ensembl_id
        string chromosome
        integer start_position
        integer end_position
        string strand
        float confidence
        jsonb provenance
        timestamp created_at
        timestamp updated_at
    }
    
    Protein {
        string id PK
        string canonical_id UK
        string name
        string uniprot_id
        string gene_id
        string sequence
        float confidence
        jsonb provenance
        timestamp created_at
        timestamp updated_at
    }
    
    Disease {
        string id PK
        string canonical_id UK
        string name
        string icd10
        string mesh_id
        text[] synonyms
        float confidence
        jsonb provenance
        timestamp created_at
        timestamp updated_at
    }
    
    Drug {
        string id PK
        string canonical_id UK
        string name
        string generic_name
        text[] brand_names
        string drug_type
        string mechanism
        string fda_status
        date approval_date
        float confidence
        jsonb provenance
        timestamp created_at
        timestamp updated_at
    }
    
    Company {
        string id PK
        string canonical_id UK
        string name
        string industry
        text[] focus_areas
        string website
        string funding_stage
        float confidence
        jsonb provenance
        timestamp created_at
        timestamp updated_at
    }
    
    Publication {
        string id PK
        string canonical_id UK
        string title
        text abstract
        text[] authors
        date publication_date
        string journal
        string doi
        string pmid
        string pmcid
        float confidence
        jsonb provenance
        timestamp created_at
        timestamp updated_at
    }
    
    Patent {
        string id PK
        string canonical_id UK
        string title
        string patent_number
        date filing_date
        date grant_date
        string assignee
        text[] claims
        float confidence
        jsonb provenance
        timestamp created_at
        timestamp updated_at
    }
    
    ClinicalTrial {
        string id PK
        string canonical_id UK
        string nct_id
        string title
        string phase
        string status
        string indication
        string sponsor
        date start_date
        date completion_date
        text primary_endpoint
        text[] secondary_endpoints
        text[] biomarkers
        float confidence
        jsonb provenance
        timestamp created_at
        timestamp updated_at
    }
    
    Conference {
        string id PK
        string canonical_id UK
        string name
        date start_date
        date end_date
        string location
        float confidence
        jsonb provenance
        timestamp created_at
        timestamp updated_at
    }
    
    Biomarker {
        string id PK
        string canonical_id UK
        string name
        string type
        string associated_disease
        float confidence
        jsonb provenance
        timestamp created_at
        timestamp updated_at
    }
    
    Pathway {
        string id PK
        string canonical_id UK
        string name
        string source
        text[] genes
        text[] proteins
        float confidence
        jsonb provenance
        timestamp created_at
        timestamp updated_at
    }
    
    Mutation {
        string id PK
        string canonical_id UK
        string name
        string gene_id
        string position
        string change
        string impact
        float confidence
        jsonb provenance
        timestamp created_at
        timestamp updated_at
    }
```

### 2.2 Graph Relationship Types

```mermaid
erDiagram
    Gene ||--|| Protein : "ENCODES"
    Protein ||--o{ Drug : "TARGETS"
    Drug ||--o{ Disease : "TREATS"
    Disease ||--o{ ClinicalTrial : "TRIAL_FOR"
    Company ||--o{ Drug : "DEVELOPS"
    Company ||--o{ Patent : "OWNS"
    Publication ||--o{ Patent : "CITES"
    Conference ||--o{ Publication : "PRESENTS_AT"
    Biomarker ||--o{ Disease : "BIOMARKER_FOR"
    Pathway ||--o{ Protein : "CONTAINS"
    Mutation ||--o{ Gene : "MUTATION_OF"
    Drug ||--o{ Drug : "COMPETES_WITH"
    Drug ||--o{ Patent : "COVERED_BY"
    Publication ||--o{ Publication : "CITES"
    Gene ||--o{ Disease : "ASSOCIATED_WITH"
    Protein ||--o{ Disease : "EXPRESSED_IN"
    ClinicalTrial ||--o{ Drug : "TESTS"
```

---

## 3. Redis Data Structures

### 3.1 Key-Value Patterns

```mermaid
erDiagram
    Session {
        string key PK "session:{session_id}"
        string user_id
        timestamp created_at
        timestamp expires_at
        jsonb metadata
        integer TTL "3600"
    }
    
    RateLimit {
        string key PK "ratelimit:{user_id}:{endpoint}"
        integer count_value
        integer TTL "60"
    }
    
    Cache {
        string key PK "cache:{service}:{resource_id}"
        string json_value
        integer TTL "300"
    }
    
    Collaboration {
        string key PK "collab:{notebook_id}:{user_id}"
        integer cursor_position
        jsonb selection
        timestamp last_activity
        integer TTL "3600"
    }
    
    AgentContext {
        string key PK "agent:context:{conversation_id}"
        jsonb messages
        jsonb tools
        jsonb variables
        integer TTL "86400"
    }
    
    InferenceCache {
        string key PK "inference:{model}:{hash_prompt}"
        string json_response
        integer TTL "3600"
    }
```

---

## 4. Cross-Database Relationships

### 4.1 PostgreSQL ↔ Neo4j

```mermaid
erDiagram
    PostgreSQL ||--|| Neo4j : "Entity Resolution"
    
    PostgreSQL {
        uuid id
        varchar canonical_id
    }
    
    Neo4j {
        string id
        string canonical_id
    }
    
    PostgreSQL "canonical_id" -- Neo4j "canonical_id" : "Mapped via entity_mappings table"
```

### 4.2 File System ↔ LLM Wiki (OKF v0.1)

```mermaid
erDiagram
    FileSystem ||--o{ OKF_Concept : "Stores"
    
    OKF_Concept {
        string file_path PK
        string type
        string title
        string description
        string resource
        string[] tags
        timestamp timestamp
        text body_markdown
    }
    
    OKF_Index {
        string file_path PK
        text content_index_table
    }
    
    OKF_Log {
        string file_path PK
        text chronological_logs
    }
```

### 4.3 PostgreSQL ↔ Redis

```mermaid
erDiagram
    PostgreSQL ||--o{ Redis : "Caching"
    
    user {
        uuid id PK
    }
    
    session {
        uuid id PK
        uuid user_id FK
    }
    
    Redis {
        string key "session:{session_id}"
        hash value
    }
```

### 4.4 PostgreSQL ↔ S3

```mermaid
erDiagram
    PostgreSQL ||--o{ S3 : "File Storage"
    
    documents_v2 {
        uuid id PK
        varchar file_path
    }
    
    docking_jobs {
        uuid id PK
        varchar protein_structure
    }
    
    S3 {
        string bucket
        string key
        binary data
    }
```

---

## 5. Data Flow Diagrams

### 5.1 Literature Ingestion Flow

```mermaid
erDiagram
    PubMed ||--o{ ingestion_jobs : "source"
    ingestion_jobs ||--o{ documents : "produces"
    documents ||--o{ extracted_entities : "contains"
    extracted_entities ||--o{ entity_mappings : "resolved to"
    entity_mappings ||--o{ graph_nodes : "maps to"
    documents ||--o{ okf_concept : "compiled to"
    documents ||--o{ document_summaries : "summarized as"
```

### 5.2 Agent Conversation Flow

```mermaid
erDiagram
    user ||--o{ conversations : "initiates"
    conversations ||--o{ messages : "contains"
    messages ||--o{ tool_calls : "triggers"
    tool_calls ||--o{ tools : "executes"
    conversations ||--o{ agent_context : "stored in"
```

### 5.3 Molecule Discovery Flow

```mermaid
erDiagram
    molecules ||--o{ docking_jobs : "docked in"
    docking_jobs ||--o{ docking_results : "produces"
    molecules ||--o{ admet_predictions : "predicted for"
    molecules ||--o{ generated_molecules : "generated as"
    generated_molecules ||--o{ portfolio_assets : "added to"
    portfolio_assets ||--o{ asset_scores : "scored by"
```

---

## 6. Index Strategy

### 6.1 PostgreSQL Indexes

| Table | Index | Type | Purpose |
|-------|-------|------|---------|
| user | idx_user_email | B-tree | Email lookup |
| session | idx_session_user_id | B-tree | User sessions |
| session | idx_session_expires_at | B-tree | Expired sessions |
| graph_nodes | idx_graph_nodes_graph_id | B-tree | Canonical ID lookup |
| graph_nodes | idx_graph_nodes_type | B-tree | Type filtering |
| graph_nodes | idx_graph_nodes_labels | GIN | Label search |
| graph_nodes | idx_graph_nodes_properties | GIN | Property search |
| documents | idx_documents_source_doc_id | B-tree | Source document lookup |
| documents | idx_documents_pmid | B-tree | PMID lookup |
| documents | idx_documents_publication_date | B-tree | Date range queries |
| extracted_entities | idx_extracted_entities_doc_id | B-tree | Document entities |
| extracted_entities | idx_extracted_entities_type | B-tree | Entity type filtering |
| conversations | idx_conversations_agent_id | B-tree | Agent conversations |
| conversations | idx_conversations_user_id | B-tree | User conversations |
| molecules | idx_molecules_canonical_smiles | B-tree | SMILES lookup |
| molecules | idx_molecules_inchi_key | B-tree | InChI key lookup |
| clinical_trials | idx_clinical_trials_nct_id | B-tree | NCT ID lookup |
| clinical_trials | idx_clinical_trials_phase | B-tree | Phase filtering |

### 6.2 Neo4j Indexes

| Label | Property | Index Type | Purpose |
|-------|-----------|------------|---------|
| Gene | canonical_id | Unique | Canonical ID lookup |
| Gene | name | Full-text | Name search |
| Drug | canonical_id | Unique | Canonical ID lookup |
| Drug | name | Full-text | Name search |
| Disease | canonical_id | Unique | Canonical ID lookup |
| Disease | name | Full-text | Name search |
| ClinicalTrial | nct_id | Unique | NCT ID lookup |
| Publication | pmid | Unique | PMID lookup |
| Publication | doi | Unique | DOI lookup |



---

## 7. Data Integrity Constraints

### 7.1 PostgreSQL Constraints

```sql
-- Foreign Key Constraints
ALTER TABLE session ADD CONSTRAINT fk_session_user_id 
    FOREIGN KEY (user_id) REFERENCES user(id) ON DELETE CASCADE;

ALTER TABLE graph_relationships ADD CONSTRAINT fk_graph_rels_from 
    FOREIGN KEY (from_node_id) REFERENCES graph_nodes(id) ON DELETE CASCADE;

ALTER TABLE graph_relationships ADD CONSTRAINT fk_graph_rels_to 
    FOREIGN KEY (to_node_id) REFERENCES graph_nodes(id) ON DELETE CASCADE;

-- Unique Constraints
ALTER TABLE user ADD CONSTRAINT uq_user_email UNIQUE (email);
ALTER TABLE graph_nodes ADD CONSTRAINT uq_graph_nodes_graph_id UNIQUE (graph_id);
ALTER TABLE documents ADD CONSTRAINT uq_documents_source_doc_id UNIQUE (source_document_id);

-- Check Constraints
ALTER TABLE user ADD CONSTRAINT chk_user_email 
    CHECK (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$');

ALTER TABLE molecules ADD CONSTRAINT chk_molecules_molecular_weight 
    CHECK (molecular_weight > 0);

ALTER TABLE clinical_predictions ADD CONSTRAINT chk_clinical_predictions_probability 
    CHECK (success_probability >= 0 AND success_probability <= 1);
```

### 7.2 Neo4j Constraints

```cypher
// Uniqueness Constraints
CREATE CONSTRAINT canonical_id_unique FOR (n:Gene) REQUIRE n.canonical_id IS UNIQUE;
CREATE CONSTRAINT canonical_id_unique FOR (n:Drug) REQUIRE n.canonical_id IS UNIQUE;
CREATE CONSTRAINT canonical_id_unique FOR (n:Disease) REQUIRE n.canonical_id IS UNIQUE;
CREATE CONSTRAINT canonical_id_unique FOR (n:Company) REQUIRE n.canonical_id IS UNIQUE;
CREATE CONSTRAINT canonical_id_unique FOR (n:Publication) REQUIRE n.canonical_id IS UNIQUE;
CREATE CONSTRAINT canonical_id_unique FOR (n:Patent) REQUIRE n.canonical_id IS UNIQUE;
CREATE CONSTRAINT canonical_id_unique FOR (n:ClinicalTrial) REQUIRE n.canonical_id IS UNIQUE;
CREATE CONSTRAINT nct_id_unique FOR (n:ClinicalTrial) REQUIRE n.nct_id IS UNIQUE;
CREATE CONSTRAINT pmid_unique FOR (n:Publication) REQUIRE n.pmid IS UNIQUE;
CREATE CONSTRAINT doi_unique FOR (n:Publication) REQUIRE n.doi IS UNIQUE;

// Node Existence Constraints
CREATE CONSTRAINT node_exists FOR (n:Gene) REQUIRE n.id IS NOT NULL;
CREATE CONSTRAINT node_exists FOR (n:Drug) REQUIRE n.id IS NOT NULL;
CREATE CONSTRAINT node_exists FOR (n:Disease) REQUIRE n.id IS NOT NULL;
```

---

## 8. Data Partitioning Strategy

### 8.1 PostgreSQL Partitioning

```sql
-- Partition audit_log by date
CREATE TABLE audit_log (
    id UUID,
    user_id UUID,
    action VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE
) PARTITION BY RANGE (created_at);

CREATE TABLE audit_log_2024_q1 PARTITION OF audit_log
    FOR VALUES FROM ('2024-01-01') TO ('2024-04-01');

CREATE TABLE audit_log_2024_q2 PARTITION OF audit_log
    FOR VALUES FROM ('2024-04-01') TO ('2024-07-01');

-- Partition documents by publication date
CREATE TABLE documents (
    id UUID,
    publication_date DATE,
    title TEXT
) PARTITION BY RANGE (publication_date);

CREATE TABLE documents_2023 PARTITION OF documents
    FOR VALUES FROM ('2023-01-01') TO ('2024-01-01');

CREATE TABLE documents_2024 PARTITION OF documents
    FOR VALUES FROM ('2024-01-01') TO ('2025-01-01');
```

### 8.2 Kafka Partitioning

| Topic | Partition Key | Partitions | Rationale |
|-------|---------------|------------|-----------|
| literature.document.ingested | document_id | 12 | Document-level ordering |
| graph.node.created | node_id | 12 | Node-level ordering |
| ai.agent.invoked | conversation_id | 12 | Conversation-level ordering |
| molecule.docking.job.submitted | job_id | 6 | Job-level ordering |
| clinical.trial.ingested | trial_id | 6 | Trial-level ordering |
