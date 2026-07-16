# Database Schemas - AI-RxOS

## Overview
AI-RxOS uses multiple database technologies optimized for different use cases:
- **PostgreSQL**: Relational data, transactions, structured queries
- **Neo4j**: Knowledge graph, relationships, graph traversals
- **LLM Wiki (OKF)**: Markdown-based persistent context, structured concepts, local search
- **Redis**: Caching, session state, real-time data
- **OpenSearch**: Full-text search, document indexing
- **Object Storage**: Files, documents, molecular structures

---

## 1. PostgreSQL Schemas

#### 1.1 Identity & Access Schema (better-auth)

#### user (better-auth core table)
```sql
CREATE TABLE user (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  email TEXT UNIQUE NOT NULL,
  email_verified BOOLEAN DEFAULT FALSE,
  name TEXT,
  avatar_url TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_user_email ON user(email);
```

#### account (better-auth OAuth provider linking)
```sql
CREATE TABLE account (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id TEXT NOT NULL,
  provider_id TEXT NOT NULL,
  user_id UUID NOT NULL REFERENCES user(id) ON DELETE CASCADE,
  access_token TEXT,
  refresh_token TEXT,
  id_token TEXT,
  expires_at TIMESTAMP WITH TIME ZONE,
  password TEXT, -- For email/password auth
  UNIQUE(account_id, provider_id)
);

CREATE INDEX idx_account_user_id ON account(user_id);
CREATE INDEX idx_account_provider_id ON account(provider_id);
```

#### session (better-auth session management)
```sql
CREATE TABLE session (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES user(id) ON DELETE CASCADE,
  expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
  ip_address TEXT,
  user_agent TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_session_user_id ON session(user_id);
CREATE INDEX idx_session_expires_at ON session(expires_at);
```

#### verification (better-auth 2FA, email verification)
```sql
CREATE TABLE verification (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  identifier TEXT NOT NULL,
  value TEXT,
  expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_verification_identifier ON verification(identifier);
CREATE INDEX idx_verification_expires_at ON verification(expires_at);
```

#### organization (better-auth organizations plugin)
```sql
CREATE TABLE organization (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  slug TEXT UNIQUE NOT NULL,
  logo_url TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_organization_slug ON organization(slug);
```

#### member (better-auth organization membership)
```sql
CREATE TABLE member (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES user(id) ON DELETE CASCADE,
  role TEXT NOT NULL DEFAULT 'member', -- 'admin', 'member'
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(organization_id, user_id)
);

CREATE INDEX idx_member_org_id ON member(organization_id);
CREATE INDEX idx_member_user_id ON member(user_id);
```

#### role (better-auth roles plugin)
```sql
CREATE TABLE role (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT UNIQUE NOT NULL,
  description TEXT,
  permissions JSONB DEFAULT '{}',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_role_name ON role(name);
```

#### user_role (better-auth role assignments)
```sql
CREATE TABLE user_role (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES user(id) ON DELETE CASCADE,
  role_id UUID NOT NULL REFERENCES role(id) ON DELETE CASCADE,
  organization_id UUID REFERENCES organization(id) ON DELETE CASCADE,
  workspace_id UUID,
  project_id UUID,
  granted_by UUID REFERENCES user(id),
  granted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  expires_at TIMESTAMP WITH TIME ZONE,
  UNIQUE(user_id, role_id, organization_id, workspace_id, project_id)
);

CREATE INDEX idx_user_role_user_id ON user_role(user_id);
CREATE INDEX idx_user_role_role_id ON user_role(role_id);
CREATE INDEX idx_user_role_org_id ON user_role(organization_id);
```

#### organizations (extended better-auth organization)
```sql
-- Note: The basic organization table is defined above with better-auth
-- This table extends it with additional AI-RxOS specific fields
ALTER TABLE organization ADD COLUMN plan TEXT DEFAULT 'free'; -- 'free', 'professional', 'enterprise'
ALTER TABLE organization ADD COLUMN max_users INTEGER DEFAULT 5;
ALTER TABLE organization ADD COLUMN max_workspaces INTEGER DEFAULT 3;
ALTER TABLE organization ADD COLUMN settings JSONB DEFAULT '{}';
ALTER TABLE organization ADD COLUMN deleted_at TIMESTAMP WITH TIME ZONE;

CREATE INDEX idx_organization_deleted_at ON organization(deleted_at) WHERE deleted_at IS NULL;
```

#### workspaces
```sql
CREATE TABLE workspace (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES organization(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT,
  settings JSONB DEFAULT '{}',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  deleted_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_workspace_org_id ON workspace(organization_id);
CREATE INDEX idx_workspace_deleted_at ON workspace(deleted_at) WHERE deleted_at IS NULL;
```

#### workspace_members
```sql
CREATE TABLE workspace_member (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES workspace(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES user(id) ON DELETE CASCADE,
  role TEXT DEFAULT 'member',
  joined_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(workspace_id, user_id)
);

CREATE INDEX idx_workspace_member_ws_id ON workspace_member(workspace_id);
CREATE INDEX idx_workspace_member_user_id ON workspace_member(user_id);
```

#### projects
```sql
CREATE TABLE project (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES workspace(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  description TEXT,
  status TEXT DEFAULT 'active', -- 'active', 'archived', 'deleted'
  settings JSONB DEFAULT '{}',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  deleted_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_project_ws_id ON project(workspace_id);
CREATE INDEX idx_project_status ON project(status);
CREATE INDEX idx_project_deleted_at ON project(deleted_at) WHERE deleted_at IS NULL;
```

#### project_members
```sql
CREATE TABLE project_member (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES user(id) ON DELETE CASCADE,
  role TEXT DEFAULT 'member',
  joined_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(project_id, user_id)
);

CREATE INDEX idx_project_member_proj_id ON project_member(project_id);
CREATE INDEX idx_project_member_user_id ON project_member(user_id);
```

#### api_keys
```sql
CREATE TABLE api_key (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES user(id) ON DELETE CASCADE,
  organization_id UUID REFERENCES organization(id) ON DELETE CASCADE,
  workspace_id UUID REFERENCES workspace(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  key_hash TEXT UNIQUE NOT NULL,
  prefix TEXT NOT NULL,
  scopes TEXT[] DEFAULT '{}',
  expires_at TIMESTAMP WITH TIME ZONE,
  last_used_at TIMESTAMP WITH TIME ZONE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  revoked_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_api_key_user_id ON api_key(user_id);
CREATE INDEX idx_api_key_prefix ON api_key(prefix);
CREATE INDEX idx_api_key_revoked_at ON api_key(revoked_at) WHERE revoked_at IS NULL;
```

#### audit_logs
```sql
CREATE TABLE audit_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES user(id) ON DELETE SET NULL,
  organization_id UUID REFERENCES organization(id) ON DELETE SET NULL,
  workspace_id UUID REFERENCES workspace(id) ON DELETE SET NULL,
  project_id UUID REFERENCES project(id) ON DELETE SET NULL,
  action TEXT NOT NULL,
  resource_type TEXT,
  resource_id UUID,
  ip_address TEXT,
  user_agent TEXT,
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_audit_log_user_id ON audit_log(user_id);
CREATE INDEX idx_audit_log_org_id ON audit_log(organization_id);
CREATE INDEX idx_audit_log_action ON audit_log(action);
CREATE INDEX idx_audit_log_created_at ON audit_log(created_at);
CREATE INDEX idx_audit_log_resource ON audit_log(resource_type, resource_id);
```

---

### 1.2 Knowledge Graph Schema

#### graph_nodes
```sql
CREATE TABLE graph_nodes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  graph_id VARCHAR(100) UNIQUE NOT NULL, -- Canonical ID from entity resolution
  type VARCHAR(50) NOT NULL, -- 'gene', 'protein', 'disease', 'drug', etc.
  labels TEXT[] NOT NULL,
  properties JSONB NOT NULL DEFAULT '{}',
  confidence FLOAT DEFAULT 1.0,
  provenance JSONB DEFAULT '{}',
  version INTEGER DEFAULT 1,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  deleted_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_graph_nodes_graph_id ON graph_nodes(graph_id);
CREATE INDEX idx_graph_nodes_type ON graph_nodes(type);
CREATE INDEX idx_graph_nodes_labels ON graph_nodes USING GIN(labels);
CREATE INDEX idx_graph_nodes_properties ON graph_nodes USING GIN(properties);
CREATE INDEX idx_graph_nodes_deleted_at ON graph_nodes(deleted_at) WHERE deleted_at IS NULL;
```

#### graph_relationships
```sql
CREATE TABLE graph_relationships (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  from_node_id UUID NOT NULL REFERENCES graph_nodes(id) ON DELETE CASCADE,
  to_node_id UUID NOT NULL REFERENCES graph_nodes(id) ON DELETE CASCADE,
  type VARCHAR(100) NOT NULL,
  properties JSONB NOT NULL DEFAULT '{}',
  confidence FLOAT DEFAULT 1.0,
  evidence JSONB DEFAULT '{}',
  provenance JSONB DEFAULT '{}',
  version INTEGER DEFAULT 1,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  deleted_at TIMESTAMP WITH TIME ZONE,
  UNIQUE(from_node_id, to_node_id, type)
);

CREATE INDEX idx_graph_rels_from ON graph_relationships(from_node_id);
CREATE INDEX idx_graph_rels_to ON graph_relationships(to_node_id);
CREATE INDEX idx_graph_rels_type ON graph_relationships(type);
CREATE INDEX idx_graph_rels_deleted_at ON graph_relationships(deleted_at) WHERE deleted_at IS NULL;
```

#### entity_mappings
```sql
CREATE TABLE entity_mappings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  canonical_id UUID NOT NULL REFERENCES graph_nodes(id) ON DELETE CASCADE,
  alias_id VARCHAR(100) NOT NULL,
  source VARCHAR(100) NOT NULL, -- 'pubmed', 'chembl', 'uniprot', etc.
  confidence FLOAT DEFAULT 1.0,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_entity_mappings_canonical ON entity_mappings(canonical_id);
CREATE INDEX idx_entity_mappings_alias ON entity_mappings(alias_id);
CREATE INDEX idx_entity_mappings_source ON entity_mappings(source);
```

#### ontologies
```sql
CREATE TABLE ontologies (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR(255) UNIQUE NOT NULL,
  version VARCHAR(50),
  source_url VARCHAR(500),
  description TEXT,
  format VARCHAR(50), -- 'owl', 'obo', 'json'
  file_path VARCHAR(500),
  imported_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_ontologies_name ON ontologies(name);
```

#### ontology_terms
```sql
CREATE TABLE ontology_terms (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ontology_id UUID NOT NULL REFERENCES ontologies(id) ON DELETE CASCADE,
  term_id VARCHAR(100) NOT NULL,
  name VARCHAR(255) NOT NULL,
  definition TEXT,
  parent_ids TEXT[] DEFAULT '{}',
  synonyms TEXT[] DEFAULT '{}',
  properties JSONB DEFAULT '{}',
  UNIQUE(ontology_id, term_id)
);

CREATE INDEX idx_ontology_terms_ontology ON ontology_terms(ontology_id);
CREATE INDEX idx_ontology_terms_term_id ON ontology_terms(term_id);
CREATE INDEX idx_ontology_terms_name ON ontology_terms(name);
CREATE INDEX idx_ontology_terms_parent_ids ON ontology_terms USING GIN(parent_ids);
```

---

### 1.3 Literature Intelligence Schema

#### ingestion_sources
```sql
CREATE TABLE ingestion_sources (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR(255) NOT NULL,
  type VARCHAR(50) NOT NULL, -- 'pubmed', 'biorxiv', 'conference', 'patent'
  config JSONB NOT NULL DEFAULT '{}',
  enabled BOOLEAN DEFAULT TRUE,
  last_sync_at TIMESTAMP WITH TIME ZONE,
  sync_schedule VARCHAR(100), -- cron expression
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_ingestion_sources_type ON ingestion_sources(type);
CREATE INDEX idx_ingestion_sources_enabled ON ingestion_sources(enabled);
```

#### ingestion_jobs
```sql
CREATE TABLE ingestion_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id UUID NOT NULL REFERENCES ingestion_sources(id) ON DELETE CASCADE,
  status VARCHAR(50) DEFAULT 'pending', -- 'pending', 'running', 'completed', 'failed'
  query TEXT,
  parameters JSONB DEFAULT '{}',
  started_at TIMESTAMP WITH TIME ZONE,
  completed_at TIMESTAMP WITH TIME ZONE,
  documents_processed INTEGER DEFAULT 0,
  documents_failed INTEGER DEFAULT 0,
  error_message TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_ingestion_jobs_source_id ON ingestion_jobs(source_id);
CREATE INDEX idx_ingestion_jobs_status ON ingestion_jobs(status);
CREATE INDEX idx_ingestion_jobs_created_at ON ingestion_jobs(created_at);
```

#### documents
```sql
CREATE TABLE documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id UUID REFERENCES ingestion_sources(id) ON DELETE SET NULL,
  source_document_id VARCHAR(255) UNIQUE NOT NULL,
  title TEXT NOT NULL,
  abstract TEXT,
  full_text TEXT,
  authors TEXT[] DEFAULT '{}',
  publication_date DATE,
  journal VARCHAR(255),
  doi VARCHAR(255),
  pmid VARCHAR(50),
  pmcid VARCHAR(50),
  url VARCHAR(500),
  document_type VARCHAR(50), -- 'article', 'preprint', 'patent', 'conference'
  language VARCHAR(10) DEFAULT 'en',
  metadata JSONB DEFAULT '{}',
  indexed_at TIMESTAMP WITH TIME ZONE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_documents_source_doc_id ON documents(source_document_id);
CREATE INDEX idx_documents_pmid ON documents(pmid);
CREATE INDEX idx_documents_doi ON documents(doi);
CREATE INDEX idx_documents_publication_date ON documents(publication_date);
CREATE INDEX idx_documents_document_type ON documents(document_type);
CREATE INDEX idx_documents_indexed_at ON documents(indexed_at);
CREATE INDEX idx_documents_metadata ON documents USING GIN(metadata);
```

#### extracted_entities
```sql
CREATE TABLE extracted_entities (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  entity_type VARCHAR(50) NOT NULL,
  entity_text VARCHAR(255) NOT NULL,
  canonical_id UUID REFERENCES graph_nodes(id) ON DELETE SET NULL,
  confidence FLOAT,
  start_position INTEGER,
  end_position INTEGER,
  extraction_model VARCHAR(100),
  extracted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_extracted_entities_doc_id ON extracted_entities(document_id);
CREATE INDEX idx_extracted_entities_type ON extracted_entities(entity_type);
CREATE INDEX idx_extracted_entities_canonical ON extracted_entities(canonical_id);
CREATE INDEX idx_extracted_entities_confidence ON extracted_entities(confidence);
```

#### extracted_relationships
```sql
CREATE TABLE extracted_relationships (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  from_entity_id UUID NOT NULL REFERENCES extracted_entities(id) ON DELETE CASCADE,
  to_entity_id UUID NOT NULL REFERENCES extracted_entities(id) ON DELETE CASCADE,
  relationship_type VARCHAR(100) NOT NULL,
  confidence FLOAT,
  evidence TEXT,
  extraction_model VARCHAR(100),
  extracted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_extracted_rels_doc_id ON extracted_relationships(document_id);
CREATE INDEX idx_extracted_rels_from ON extracted_relationships(from_entity_id);
CREATE INDEX idx_extracted_rels_to ON extracted_relationships(to_entity_id);
CREATE INDEX idx_extracted_rels_type ON extracted_relationships(relationship_type);
```

#### document_summaries
```sql
CREATE TABLE document_summaries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  summary TEXT NOT NULL,
  key_points TEXT[] DEFAULT '{}',
  summary_model VARCHAR(100),
  confidence FLOAT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(document_id)
);

CREATE INDEX idx_doc_summaries_doc_id ON document_summaries(document_id);
```

#### duplicate_groups
```sql
CREATE TABLE duplicate_groups (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  representative_document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  similarity_threshold FLOAT DEFAULT 0.9,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_duplicate_groups_rep ON duplicate_groups(representative_document_id);
```

#### duplicate_group_members
```sql
CREATE TABLE duplicate_group_members (
  group_id UUID NOT NULL REFERENCES duplicate_groups(id) ON DELETE CASCADE,
  document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  similarity FLOAT NOT NULL,
  PRIMARY KEY (group_id, document_id)
);

CREATE INDEX idx_dup_group_members_group ON duplicate_group_members(group_id);
CREATE INDEX idx_dup_group_members_doc ON duplicate_group_members(document_id);
```

#### novelty_scores
```sql
CREATE TABLE novelty_scores (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  novelty_score FLOAT NOT NULL,
  aspects JSONB DEFAULT '{}',
  scoring_model VARCHAR(100),
  scored_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(document_id)
);

CREATE INDEX idx_novelty_scores_doc_id ON novelty_scores(document_id);
CREATE INDEX idx_novelty_scores_score ON novelty_scores(novelty_score);
```

---

### 1.4 AI Orchestration Schema

#### agents
```sql
CREATE TABLE agents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR(255) NOT NULL,
  type VARCHAR(100) NOT NULL, -- 'literature', 'target_discovery', 'molecule_discovery', etc.
  description TEXT,
  config JSONB NOT NULL DEFAULT '{}',
  model_id UUID,
  system_prompt TEXT,
  tools JSONB DEFAULT '{}',
  enabled BOOLEAN DEFAULT TRUE,
  version INTEGER DEFAULT 1,
  created_by UUID REFERENCES user(id) ON DELETE SET NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_agents_type ON agents(type);
CREATE INDEX idx_agents_enabled ON agents(enabled);
```

#### conversations
```sql
CREATE TABLE conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  agent_id UUID NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
  user_id UUID REFERENCES user(id) ON DELETE SET NULL,
  workspace_id UUID REFERENCES workspace(id) ON DELETE SET NULL,
  project_id UUID REFERENCES project(id) ON DELETE SET NULL,
  title VARCHAR(255),
  status VARCHAR(50) DEFAULT 'active', -- 'active', 'archived', 'deleted'
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_conversations_agent_id ON conversations(agent_id);
CREATE INDEX idx_conversations_user_id ON conversations(user_id);
CREATE INDEX idx_conversations_workspace_id ON conversations(workspace_id);
CREATE INDEX idx_conversations_status ON conversations(status);
```

#### messages
```sql
CREATE TABLE messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role VARCHAR(50) NOT NULL, -- 'user', 'assistant', 'system', 'tool'
  content TEXT NOT NULL,
  tool_calls JSONB DEFAULT '{}',
  metadata JSONB DEFAULT '{}',
  token_count INTEGER,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_messages_conversation_id ON messages(conversation_id);
CREATE INDEX idx_messages_created_at ON messages(created_at);
```

#### tool_calls
```sql
CREATE TABLE tool_calls (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  message_id UUID NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  tool_id VARCHAR(255) NOT NULL,
  tool_name VARCHAR(255) NOT NULL,
  parameters JSONB NOT NULL DEFAULT '{}',
  result TEXT,
  error_message TEXT,
  status VARCHAR(50) DEFAULT 'pending', -- 'pending', 'running', 'completed', 'failed'
  started_at TIMESTAMP WITH TIME ZONE,
  completed_at TIMESTAMP WITH TIME ZONE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_tool_calls_message_id ON tool_calls(message_id);
CREATE INDEX idx_tool_calls_status ON tool_calls(status);
```

#### models
```sql
CREATE TABLE models (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR(255) NOT NULL,
  type VARCHAR(50) NOT NULL, -- 'llm', 'embedding', 'graph_neural_network', 'protein_lm', etc.
  framework VARCHAR(50), -- 'pytorch', 'tensorflow', 'onnx'
  description TEXT,
  config JSONB NOT NULL DEFAULT '{}',
  status VARCHAR(50) DEFAULT 'registered', -- 'registered', 'deployed', 'deprecated'
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_models_type ON models(type);
CREATE INDEX idx_models_status ON models(status);
```

#### model_versions
```sql
CREATE TABLE model_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  model_id UUID NOT NULL REFERENCES models(id) ON DELETE CASCADE,
  version VARCHAR(50) NOT NULL,
  artifact_uri VARCHAR(500) NOT NULL,
  config JSONB NOT NULL DEFAULT '{}',
  metrics JSONB DEFAULT '{}',
  deployed BOOLEAN DEFAULT FALSE,
  deployment_config JSONB DEFAULT '{}',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(model_id, version)
);

CREATE INDEX idx_model_versions_model_id ON model_versions(model_id);
CREATE INDEX idx_model_versions_deployed ON model_versions(deployed);
```

#### model_evaluations
```sql
CREATE TABLE model_evaluations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  model_version_id UUID NOT NULL REFERENCES model_versions(id) ON DELETE CASCADE,
  dataset_name VARCHAR(255),
  metrics JSONB NOT NULL DEFAULT '{}',
  evaluation_type VARCHAR(100),
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_model_evaluations_version ON model_evaluations(model_version_id);
```

#### prompts
```sql
CREATE TABLE prompts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR(255) NOT NULL,
  description TEXT,
  template TEXT NOT NULL,
  variables JSONB DEFAULT '{}',
  version INTEGER DEFAULT 1,
  created_by UUID REFERENCES user(id) ON DELETE SET NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_prompts_name ON prompts(name);
```

#### prompt_versions
```sql
CREATE TABLE prompt_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  prompt_id UUID NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
  version INTEGER NOT NULL,
  template TEXT NOT NULL,
  variables JSONB DEFAULT '{}',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(prompt_id, version)
);

CREATE INDEX idx_prompt_versions_prompt_id ON prompt_versions(prompt_id);
```

#### tools
```sql
CREATE TABLE tools (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR(255) UNIQUE NOT NULL,
  description TEXT,
  type VARCHAR(50) NOT NULL, -- 'function', 'api', 'database', 'agent'
  config JSONB NOT NULL DEFAULT '{}',
  schema JSONB NOT NULL DEFAULT '{}',
  rate_limit INTEGER,
  enabled BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_tools_type ON tools(type);
CREATE INDEX idx_tools_enabled ON tools(enabled);
```

---

### 1.5 Molecule Discovery Schema

#### molecules
```sql
CREATE TABLE molecules (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  smiles VARCHAR(500) NOT NULL,
  canonical_smiles VARCHAR(500) UNIQUE NOT NULL,
  inchi VARCHAR(1000),
  inchi_key VARCHAR(50),
  name VARCHAR(255),
  molecular_formula VARCHAR(100),
  molecular_weight FLOAT,
  properties JSONB DEFAULT '{}', -- logp, tpsa, hbd, hba, etc.
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_molecules_smiles ON molecules(smiles);
CREATE INDEX idx_molecules_canonical_smiles ON molecules(canonical_smiles);
CREATE INDEX idx_molecules_inchi_key ON molecules(inchi_key);
CREATE INDEX idx_molecules_mw ON molecules(molecular_weight);
CREATE INDEX idx_molecules_properties ON molecules USING GIN(properties);
```

#### docking_jobs
```sql
CREATE TABLE docking_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  target_id UUID NOT NULL,
  ligand_smiles VARCHAR(500) NOT NULL,
  protein_structure VARCHAR(500),
  status VARCHAR(50) DEFAULT 'queued', -- 'queued', 'running', 'completed', 'failed'
  parameters JSONB DEFAULT '{}',
  started_at TIMESTAMP WITH TIME ZONE,
  completed_at TIMESTAMP WITH TIME ZONE,
  error_message TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_docking_jobs_target_id ON docking_jobs(target_id);
CREATE INDEX idx_docking_jobs_status ON docking_jobs(status);
CREATE INDEX idx_docking_jobs_created_at ON docking_jobs(created_at);
```

#### docking_results
```sql
CREATE TABLE docking_results (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id UUID NOT NULL REFERENCES docking_jobs(id) ON DELETE CASCADE,
  pose_rank INTEGER NOT NULL,
  score FLOAT NOT NULL,
  rmsd FLOAT,
  pose_data JSONB NOT NULL, -- coordinates
  interactions JSONB DEFAULT '{}',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_docking_results_job_id ON docking_results(job_id);
CREATE INDEX idx_docking_results_score ON docking_results(score);
```

#### admet_predictions
```sql
CREATE TABLE admet_predictions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  molecule_id UUID NOT NULL REFERENCES molecules(id) ON DELETE CASCADE,
  property_name VARCHAR(100) NOT NULL,
  property_value FLOAT,
  property_unit VARCHAR(50),
  prediction_class VARCHAR(50), -- 'high', 'medium', 'low'
  confidence FLOAT,
  model_version VARCHAR(100),
  predicted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(molecule_id, property_name)
);

CREATE INDEX idx_admet_molecule_id ON admet_predictions(molecule_id);
CREATE INDEX idx_admet_property_name ON admet_predictions(property_name);
```

#### generated_molecules
```sql
CREATE TABLE generated_molecules (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  generation_job_id UUID NOT NULL,
  smiles VARCHAR(500) NOT NULL,
  canonical_smiles VARCHAR(500),
  properties JSONB DEFAULT '{}',
  scores JSONB DEFAULT '{}', -- novelty, druglikeness, etc.
  selected BOOLEAN DEFAULT FALSE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_generated_molecules_job_id ON generated_molecules(generation_job_id);
CREATE INDEX idx_generated_molecules_selected ON generated_molecules(selected);
```

---

### 1.6 Clinical Intelligence Schema

#### clinical_trials
```sql
CREATE TABLE clinical_trials (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nct_id VARCHAR(50) UNIQUE NOT NULL,
  title TEXT NOT NULL,
  phase VARCHAR(50), -- 'Phase I', 'Phase II', 'Phase III', 'Phase IV'
  status VARCHAR(50), -- 'Recruiting', 'Active', 'Completed', etc.
  indication VARCHAR(255),
  sponsor VARCHAR(255),
  start_date DATE,
  completion_date DATE,
  primary_endpoint TEXT,
  secondary_endpoints TEXT[],
  biomarkers TEXT[],
  enrollment INTEGER,
  locations JSONB DEFAULT '{}',
  url VARCHAR(500),
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_clinical_trials_nct_id ON clinical_trials(nct_id);
CREATE INDEX idx_clinical_trials_phase ON clinical_trials(phase);
CREATE INDEX idx_clinical_trials_status ON clinical_trials(status);
CREATE INDEX idx_clinical_trials_indication ON clinical_trials(indication);
CREATE INDEX idx_clinical_trials_sponsor ON clinical_trials(sponsor);
```

#### clinical_predictions
```sql
CREATE TABLE clinical_predictions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  trial_id UUID REFERENCES clinical_trials(id) ON DELETE SET NULL,
  drug_id UUID,
  indication VARCHAR(255),
  phase VARCHAR(50),
  success_probability FLOAT NOT NULL,
  confidence FLOAT,
  factors JSONB DEFAULT '{}',
  model_version VARCHAR(100),
  predicted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_clinical_predictions_trial_id ON clinical_predictions(trial_id);
CREATE INDEX idx_clinical_predictions_indication ON clinical_predictions(indication);
CREATE INDEX idx_clinical_predictions_phase ON clinical_predictions(phase);
```

---

### 1.7 Competitive Intelligence Schema

#### competitors
```sql
CREATE TABLE competitors (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR(255) NOT NULL,
  industry VARCHAR(100),
  focus_areas TEXT[] DEFAULT '{}',
  website VARCHAR(500),
  funding_stage VARCHAR(100),
  description TEXT,
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_competitors_name ON competitors(name);
CREATE INDEX idx_competitors_industry ON competitors(industry);
CREATE INDEX idx_competitors_focus_areas ON competitors USING GIN(focus_areas);
```

#### competitor_assets
```sql
CREATE TABLE competitor_assets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  competitor_id UUID NOT NULL REFERENCES competitors(id) ON DELETE CASCADE,
  name VARCHAR(255) NOT NULL,
  type VARCHAR(50), -- 'small_molecule', 'biologic', 'cell_therapy', etc.
  indication VARCHAR(255),
  phase VARCHAR(50),
  mechanism VARCHAR(255),
  status VARCHAR(50),
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_competitor_assets_comp_id ON competitor_assets(competitor_id);
CREATE INDEX idx_competitor_assets_phase ON competitor_assets(phase);
CREATE INDEX idx_competitor_assets_indication ON competitor_assets(indication);
```

#### competitor_events
```sql
CREATE TABLE competitor_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  competitor_id UUID NOT NULL REFERENCES competitors(id) ON DELETE CASCADE,
  event_type VARCHAR(100) NOT NULL, -- 'funding', 'leadership', 'trial_update', 'patent', etc.
  title TEXT NOT NULL,
  description TEXT,
  event_date DATE,
  source_url VARCHAR(500),
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_competitor_events_comp_id ON competitor_events(competitor_id);
CREATE INDEX idx_competitor_events_type ON competitor_events(event_type);
CREATE INDEX idx_competitor_events_date ON competitor_events(event_date);
```

---

### 1.8 Portfolio Management Schema

#### portfolios
```sql
CREATE TABLE portfolios (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES workspace(id) ON DELETE CASCADE,
  name VARCHAR(255) NOT NULL,
  description TEXT,
  status VARCHAR(50) DEFAULT 'active', -- 'active', 'archived'
  settings JSONB DEFAULT '{}',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_portfolios_workspace_id ON portfolios(workspace_id);
CREATE INDEX idx_portfolios_status ON portfolios(status);
```

#### portfolio_assets
```sql
CREATE TABLE portfolio_assets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  portfolio_id UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
  name VARCHAR(255) NOT NULL,
  type VARCHAR(50), -- 'internal', 'external', 'licensing_opportunity'
  asset_type VARCHAR(50), -- 'small_molecule', 'biologic', etc.
  indication VARCHAR(255),
  phase VARCHAR(50),
  mechanism VARCHAR(255),
  company VARCHAR(255),
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_portfolio_assets_portfolio_id ON portfolio_assets(portfolio_id);
CREATE INDEX idx_portfolio_assets_type ON portfolio_assets(type);
CREATE INDEX idx_portfolio_assets_phase ON portfolio_assets(phase);
```

#### asset_scores
```sql
CREATE TABLE asset_scores (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  asset_id UUID NOT NULL REFERENCES portfolio_assets(id) ON DELETE CASCADE,
  dimension VARCHAR(100) NOT NULL, -- 'scientific', 'commercial', 'technical', etc.
  score FLOAT NOT NULL,
  weight FLOAT DEFAULT 1.0,
  explanation TEXT,
  factors JSONB DEFAULT '{}',
  scored_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(asset_id, dimension)
);

CREATE INDEX idx_asset_scores_asset_id ON asset_scores(asset_id);
CREATE INDEX idx_asset_scores_dimension ON asset_scores(dimension);
```

#### portfolio_scores
```sql
CREATE TABLE portfolio_scores (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  portfolio_id UUID NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
  composite_score FLOAT NOT NULL,
  risk_score FLOAT,
  roi_potential FLOAT,
  diversification FLOAT,
  balance FLOAT,
  scored_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_portfolio_scores_portfolio_id ON portfolio_scores(portfolio_id);
```

---

### 1.9 Collaboration Schema

#### notebooks
```sql
CREATE TABLE notebooks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES project(id) ON DELETE CASCADE,
  title VARCHAR(255) NOT NULL,
  description TEXT,
  owner_id UUID NOT NULL REFERENCES user(id) ON DELETE CASCADE,
  tags TEXT[] DEFAULT '{}',
  settings JSONB DEFAULT '{}',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  deleted_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_notebooks_project_id ON notebooks(project_id);
CREATE INDEX idx_notebooks_owner_id ON notebooks(owner_id);
CREATE INDEX idx_notebooks_tags ON notebooks USING GIN(tags);
CREATE INDEX idx_notebooks_deleted_at ON notebooks(deleted_at) WHERE deleted_at IS NULL;
```

#### notebook_cells
```sql
CREATE TABLE notebook_cells (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  notebook_id UUID NOT NULL REFERENCES notebooks(id) ON DELETE CASCADE,
  cell_type VARCHAR(50) NOT NULL, -- 'markdown', 'code', 'raw'
  content TEXT NOT NULL,
  position INTEGER NOT NULL,
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_notebook_cells_notebook_id ON notebook_cells(notebook_id);
CREATE INDEX idx_notebook_cells_position ON notebook_cells(notebook_id, position);
```

#### notebook_versions
```sql
CREATE TABLE notebook_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  notebook_id UUID NOT NULL REFERENCES notebooks(id) ON DELETE CASCADE,
  version INTEGER NOT NULL,
  snapshot JSONB NOT NULL,
  created_by UUID REFERENCES user(id) ON DELETE SET NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(notebook_id, version)
);

CREATE INDEX idx_notebook_versions_notebook_id ON notebook_versions(notebook_id);
```

#### notebook_collaborators
```sql
CREATE TABLE notebook_collaborators (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  notebook_id UUID NOT NULL REFERENCES notebooks(id) ON DELETE CASCADE,
  user_id UUID NOT NULL REFERENCES user(id) ON DELETE CASCADE,
  role VARCHAR(50) DEFAULT 'editor', -- 'owner', 'editor', 'viewer'
  joined_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(notebook_id, user_id)
);

CREATE INDEX idx_notebook_collaborators_notebook_id ON notebook_collaborators(notebook_id);
CREATE INDEX idx_notebook_collaborators_user_id ON notebook_collaborators(user_id);
```

#### documents
```sql
CREATE TABLE documents_v2 (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  workspace_id UUID NOT NULL REFERENCES workspace(id) ON DELETE CASCADE,
  folder_id UUID REFERENCES documents_v2(id) ON DELETE CASCADE,
  name VARCHAR(255) NOT NULL,
  type VARCHAR(50) NOT NULL, -- 'pdf', 'docx', 'pptx', 'csv', etc.
  size BIGINT,
  file_path VARCHAR(500),
  owner_id UUID NOT NULL REFERENCES user(id) ON DELETE CASCADE,
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  deleted_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_documents_v2_workspace_id ON documents_v2(workspace_id);
CREATE INDEX idx_documents_v2_folder_id ON documents_v2(folder_id);
CREATE INDEX idx_documents_v2_owner_id ON documents_v2(owner_id);
CREATE INDEX idx_documents_v2_deleted_at ON documents_v2(deleted_at) WHERE deleted_at IS NULL;
```

#### document_versions
```sql
CREATE TABLE document_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID NOT NULL REFERENCES documents_v2(id) ON DELETE CASCADE,
  version INTEGER NOT NULL,
  file_path VARCHAR(500),
  size BIGINT,
  created_by UUID REFERENCES user(id) ON DELETE SET NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  UNIQUE(document_id, version)
);

CREATE INDEX idx_document_versions_document_id ON document_versions(document_id);
```

#### reports
```sql
CREATE TABLE reports (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR(255) NOT NULL,
  type VARCHAR(50) NOT NULL, -- 'scientific', 'competitive', 'due_diligence', 'executive'
  template_id UUID,
  parameters JSONB DEFAULT '{}',
  status VARCHAR(50) DEFAULT 'pending', -- 'pending', 'generating', 'completed', 'failed'
  file_path VARCHAR(500),
  generated_by UUID REFERENCES user(id) ON DELETE SET NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  completed_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_reports_type ON reports(type);
CREATE INDEX idx_reports_status ON reports(status);
CREATE INDEX idx_reports_generated_by ON reports(generated_by);
```

---

### 1.10 Data Integration Schema

#### connectors
```sql
CREATE TABLE connectors (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name VARCHAR(255) NOT NULL,
  type VARCHAR(100) NOT NULL, -- 'pubmed', 'chembl', 'drugbank', 'clinicaltrials_gov'
  config JSONB NOT NULL DEFAULT '{}',
  enabled BOOLEAN DEFAULT TRUE,
  health_status VARCHAR(50) DEFAULT 'unknown', -- 'healthy', 'unhealthy', 'unknown'
  last_health_check TIMESTAMP WITH TIME ZONE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_connectors_type ON connectors(type);
CREATE INDEX idx_connectors_enabled ON connectors(enabled);
```

#### transformations
```sql
CREATE TABLE transformations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  connector_id UUID NOT NULL REFERENCES connectors(id) ON DELETE CASCADE,
  name VARCHAR(255) NOT NULL,
  source_schema JSONB NOT NULL,
  target_schema JSONB NOT NULL,
  mapping_rules JSONB NOT NULL,
  validation_rules JSONB DEFAULT '{}',
  enabled BOOLEAN DEFAULT TRUE,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_transformations_connector_id ON transformations(connector_id);
```

---

### 1.11 Observability Schema

#### health_history
```sql
CREATE TABLE health_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  service_name VARCHAR(255) NOT NULL,
  status VARCHAR(50) NOT NULL, -- 'healthy', 'unhealthy', 'degraded'
  latency_ms INTEGER,
  error_message TEXT,
  metadata JSONB DEFAULT '{}',
  checked_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_health_check_service ON health_history(service_name);
CREATE INDEX idx_health_check_status ON health_history(status);
CREATE INDEX idx_health_check_checked_at ON health_history(checked_at);
```

---

## 2. Neo4j Schema

### Graph Structure

Neo4j stores the knowledge graph with the following node labels and relationship types:

#### Node Labels

- **Gene**: Gene entities
- **Protein**: Protein entities
- **Disease**: Disease entities
- **Drug**: Drug/compound entities
- **Target**: Therapeutic target entities
- **Company**: Pharmaceutical/biotech companies
- **Publication**: Scientific publications
- **Patent**: Patent documents
- **ClinicalTrial**: Clinical trial records
- **Conference**: Conference events
- **Biomarker**: Biomarker entities
- **Pathway**: Biological pathways
- **Mutation**: Genetic mutations

#### Relationship Types

- **TARGETS**: Drug targets a protein/gene
- **TREATS**: Drug treats a disease
- **INTERACTS**: Protein-protein interactions
- **PUBLISHED_IN**: Publication published in journal
- **PRESENTED_AT**: Publication presented at conference
- **OWNED_BY**: Patent owned by company
- **COMPETES_WITH**: Drug competes with another drug
- **LICENSED_BY**: Drug licensed by company
- **EXPRESSED_IN**: Gene/protein expressed in tissue
- **VALIDATED_BY**: Target validated by evidence
- **ASSOCIATED_WITH**: Gene associated with disease
- **PATHWAY_MEMBER**: Member of biological pathway
- **MUTATED_IN**: Gene mutated in disease
- **TRIAL_FOR**: Clinical trial for drug
- **CITES**: Publication cites another publication

#### Node Properties (Common)

```cypher
// Common properties for all nodes
id: String (UUID)
canonical_id: String
name: String
aliases: [String]
confidence: Float
provenance: Map
created_at: DateTime
updated_at: DateTime
```

#### Example Node Schemas

```cypher
// Gene
(:Gene {
  id: "uuid",
  canonical_id: "gene:BRCA1",
  name: "BRCA1",
  symbol: "BRCA1",
  entrez_id: "672",
  ensembl_id: "ENSG00000012048",
  chromosome: "17",
  start_position: 43044295,
  end_position: 43125483,
  strand: "+",
  confidence: 1.0,
  provenance: {source: "ncbi", version: "2024.01"},
  created_at: datetime(),
  updated_at: datetime()
})

// Drug
(:Drug {
  id: "uuid",
  canonical_id: "drug:trastuzumab",
  name: "Trastuzumab",
  generic_name: "Trastuzumab",
  brand_names: ["Herceptin"],
  drug_type: "biologic",
  mechanism: "HER2 inhibitor",
  fda_status: "approved",
  approval_date: date("1998-09-25"),
  confidence: 1.0,
  provenance: {source: "drugbank", version: "2024.01"},
  created_at: datetime(),
  updated_at: datetime()
})

// Disease
(:Disease {
  id: "uuid",
  canonical_id: "disease:breast_cancer",
  name: "Breast Cancer",
  icd10: "C50",
  mesh_id: "D001943",
  synonyms: ["Breast carcinoma", "Mammary carcinoma"],
  confidence: 1.0,
  provenance: {source: "mesh", version: "2024.01"},
  created_at: datetime(),
  updated_at: datetime()
})

// ClinicalTrial
(:ClinicalTrial {
  id: "uuid",
  canonical_id: "trial:NCT12345678",
  nct_id: "NCT12345678",
  title: "Study of Drug X",
  phase: "Phase II",
  status: "Recruiting",
  indication: "Breast Cancer",
  start_date: date("2024-01-01"),
  confidence: 1.0,
  provenance: {source: "clinicaltrials_gov"},
  created_at: datetime(),
  updated_at: datetime()
})
```

#### Relationship Properties

```cypher
// TARGETS relationship
(:Drug)-[:TARGETS {
  confidence: Float,
  mechanism: String,
  evidence: [String],
  provenance: Map,
  created_at: DateTime
}]->(:Protein)

// TREATS relationship
(:Drug)-[:TREATS {
  confidence: Float,
  phase: String,
  approval_status: String,
  evidence: [String],
  provenance: Map,
  created_at: DateTime
}]->(:Disease)

// CITES relationship
(:Publication)-[:CITES {
  citation_count: Integer,
  context: String,
  provenance: Map,
  created_at: DateTime
}]->(:Publication)
```

#### Graph Constraints

```cypher
// Uniqueness constraints
CREATE CONSTRAINT canonical_id_unique IF NOT EXISTS FOR (n:Gene) REQUIRE n.canonical_id IS UNIQUE;
CREATE CONSTRAINT canonical_id_unique IF NOT EXISTS FOR (n:Drug) REQUIRE n.canonical_id IS UNIQUE;
CREATE CONSTRAINT canonical_id_unique IF NOT EXISTS FOR (n:Disease) REQUIRE n.canonical_id IS UNIQUE;
// ... similar for other node types

// Indexes
CREATE INDEX gene_name IF NOT EXISTS FOR (n:Gene) ON (n.name);
CREATE INDEX drug_name IF NOT EXISTS FOR (n:Drug) ON (n.name);
CREATE INDEX disease_name IF NOT EXISTS FOR (n:Disease) ON (n.name);
CREATE INDEX trial_nct_id IF NOT EXISTS FOR (n:ClinicalTrial) ON (n.nct_id);
// ... similar for other properties
```

---

## 3. LLM Wiki (Open Knowledge Format v0.1)

Rather than storing vector embeddings in a database table, the system uses a shared storage volume organized as a living wiki conforming to the Open Knowledge Format (OKF v0.1) specification.

### 3.1 OKF Directory Structure
```
wiki-root/
├── raw/                      # Curated immutable raw source files (PDFs, papers, logs)
│   ├── pub_her2_2026.pdf
│   └── trial_nct0011.txt
└── wiki/                     # Compiled markdown concept pages
    ├── index.md              # Content catalog of all concept pages
    ├── log.md                # Chronological append-only change log
    ├── genes/
    │   ├── HER2.md
    │   └── BRCA1.md
    ├── drugs/
    │   └── Trastuzumab.md
    └── trials/
        └── NCT001122.md
```

### 3.2 OKF Concept File Specification
Each concept file is a single Markdown page containing YAML frontmatter and a structured body.

#### Sample Concept: `wiki/genes/HER2.md`
```markdown
---
type: Gene
title: HER2 (ERBB2)
description: Human Epidermal Growth Factor Receptor 2, oncogene amplified in breast cancer.
resource: https://www.uniprot.org/uniprotkb/P04626/entry
tags: [gene, oncology, receptor]
timestamp: 2026-07-16T20:11:00Z
---
# Overview
HER2 is a member of the epidermal growth factor receptor (EGFR) family. Its amplification is associated with aggressive breast and ovarian cancers.

# Target Therapies
- [Trastuzumab](/wiki/drugs/Trastuzumab.md): Monoclonal antibody targeting the extracellular domain of HER2.
- Lapatinib: Tyrosine kinase inhibitor targeting EGFR/HER2.

# References
- Raw source: [pub_her2_2026.pdf](/raw/pub_her2_2026.pdf)
```

### 3.3 Index and Log Schema

#### Content Index: `wiki/index.md`
```markdown
# Content Index

| Path | Type | Title | Description | Tags |
|------|------|-------|-------------|------|
| [/wiki/genes/HER2.md](/wiki/genes/HER2.md) | Gene | HER2 | EGFR receptor family gene | gene, oncology |
| [/wiki/drugs/Trastuzumab.md](/wiki/drugs/Trastuzumab.md) | Drug | Trastuzumab | Anti-HER2 monoclonal antibody | drug, oncology |
```

#### Chronological Log: `wiki/log.md`
```markdown
# Chronological Log

## [2026-07-16] ingest | HER2 Gene Profile
- Ingested source: [pub_her2_2026.pdf](/raw/pub_her2_2026.pdf)
- Created concept: [/wiki/genes/HER2.md](/wiki/genes/HER2.md)
- Updated index and cross-references.

## [2026-07-15] ingest | Trastuzumab Drug Profile
- Created concept: [/wiki/drugs/Trastuzumab.md](/wiki/drugs/Trastuzumab.md)
```

---

## 4. Redis Schemas

### Key Patterns

#### Session Storage
```
session:{session_id} -> Hash {
  user_id: "uuid",
  created_at: timestamp,
  expires_at: timestamp,
  metadata: json
}
TTL: 3600 (1 hour)
```

#### Rate Limiting
```
ratelimit:{user_id}:{endpoint} -> String (count)
TTL: 60 (1 minute)
```

#### Cache
```
cache:{service}:{resource_id} -> String (JSON)
TTL: 300 (5 minutes)
```

#### Real-time Collaboration
```
collab:{notebook_id}:{user_id} -> Hash {
  cursor_position: integer,
  selection: json,
  last_activity: timestamp
}
TTL: 3600 (1 hour)
```

#### Agent Context
```
agent:context:{conversation_id} -> Hash {
  messages: json,
  tools: json,
  variables: json
}
TTL: 86400 (24 hours)
```

#### Inference Cache
```
inference:{model}:{hash(prompt)} -> String (JSON response)
TTL: 3600 (1 hour)
```

---

## 5. OpenSearch Schema

### Document Index

```json
PUT /documents
{
  "mappings": {
    "properties": {
      "id": {"type": "keyword"},
      "title": {
        "type": "text",
        "fields": {
          "keyword": {"type": "keyword"},
          "english": {"type": "text", "analyzer": "english"}
        }
      },
      "abstract": {
        "type": "text",
        "fields": {
          "english": {"type": "text", "analyzer": "english"}
        }
      },
      "full_text": {
        "type": "text",
        "fields": {
          "english": {"type": "text", "analyzer": "english"}
        }
      },
      "authors": {"type": "keyword"},
      "publication_date": {"type": "date"},
      "journal": {"type": "keyword"},
      "document_type": {"type": "keyword"},
      "entities": {
        "type": "nested",
        "properties": {
          "type": {"type": "keyword"},
          "text": {"type": "text"},
          "canonical_id": {"type": "keyword"}
        }
      },
      "tags": {"type": "keyword"},
      "created_at": {"type": "date"},
      "updated_at": {"type": "date"}
    }
  },
  "settings": {
    "number_of_shards": 3,
    "number_of_replicas": 2,
    "analysis": {
      "analyzer": {
        "english": {
          "type": "standard",
          "stopwords": "_english_"
        }
      }
    }
  }
}
```

### Knowledge Graph Index

```json
PUT /graph_nodes
{
  "mappings": {
    "properties": {
      "id": {"type": "keyword"},
      "graph_id": {"type": "keyword"},
      "type": {"type": "keyword"},
      "labels": {"type": "keyword"},
      "name": {
        "type": "text",
        "fields": {
          "keyword": {"type": "keyword"}
        }
      },
      "properties": {"type": "object"},
      "confidence": {"type": "float"},
      "created_at": {"type": "date"},
      "updated_at": {"type": "date"}
    }
  }
}
```

---

## 6. Object Storage Schema

### Bucket Structure

```
ai-rxos/
├── documents/
│   ├── {document_id}/
│   │   ├── original.pdf
│   │   ├── processed/
│   │   └── thumbnails/
├── molecules/
│   ├── {molecule_id}/
│   │   ├── structure.sdf
│   │   ├── structure.mol2
│   │   └── images/
├── proteins/
│   ├── {protein_id}/
│   │   ├── structure.pdb
│   │   └── binding_pockets/
├── docking/
│   ├── {job_id}/
│   │   ├── poses/
│   │   └── results/
├── reports/
│   ├── {report_id}/
│   │   └── output.pdf
└── exports/
    ├── {notebook_id}/
    │   ├── pdf/
    │   ├── docx/
    │   └── html/
```

### Metadata Storage

Each object in storage has associated metadata stored in PostgreSQL or as object metadata:
- Content-Type
- Upload timestamp
- Uploader user ID
- File size
- Checksum (MD5, SHA256)
- Tags
- Custom metadata

---

## 7. Data Migration Strategy

### Version Control
- All schema changes tracked via migration scripts
- Migration scripts stored in `migrations/` directory
- Naming convention: `YYYYMMDDHHMMSS_description.sql`
- Use a migration tool (Flyway, Liquibase, or custom)

### Rollback Strategy
- Each migration includes rollback script
- Test migrations in staging before production
- Use blue-green deployment for zero-downtime migrations

### Backup Strategy
- Daily full backups of PostgreSQL
- Continuous WAL archiving
- Weekly full backups of Neo4j
- Daily incremental backups of Neo4j
- Cross-region replication of all backups

---

## 8. Data Retention Policy

### PostgreSQL
- Audit logs: 7 years (compliance)
- User data: 30 days after account deletion
- Session data: 30 days
- Temporary data: 7 days

### Neo4j
- Graph versions: Keep latest 10 versions
- Deleted nodes: Soft delete, purge after 90 days

### Redis
- All data: TTL-based, max 24 hours
- Session data: 1 hour TTL

### OpenSearch
- Document indices: Keep all
- Log indices: 30 days retention

### Object Storage
- User uploads: 90 days after account deletion
- Temporary files: 7 days
- Reports: 1 year
