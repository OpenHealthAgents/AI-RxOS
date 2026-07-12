# Event-Driven Architecture - AI-RxOS

## Overview
AI-RxOS uses an event-driven architecture with Kafka as the primary message broker for asynchronous communication between services. Events enable loose coupling, scalability, and real-time data flow across the system.

---

## Event Bus Configuration

### Kafka Cluster
- **Brokers**: 3-node cluster (minimum for HA)
- **Replication Factor**: 3
- **Partitions**: Configured per topic based on throughput
- **Retention**: 7 days default, configurable per topic
- **Compression**: lz4
- **Security**: TLS + SASL/SCRAM

### Topic Naming Convention
- Format: `{domain}.{entity}.{action}`
- Examples: `literature.document.ingested`, `graph.node.created`, `agent.tool.invoked`

---

## Event Schema

### Standard Event Format
```json
{
  "event_id": "uuid",
  "event_type": "string",
  "event_version": "string",
  "source": "string",
  "timestamp": "ISO8601",
  "correlation_id": "uuid",
  "causation_id": "uuid",
  "data": {},
  "metadata": {}
}
```

### Event Metadata
```json
{
  "user_id": "uuid",
  "organization_id": "uuid",
  "workspace_id": "uuid",
  "project_id": "uuid",
  "trace_id": "string",
  "span_id": "string"
}
```

---

## Event Catalog

### 1. Identity & Access Events

#### user.created
```json
{
  "event_type": "identity.user.created",
  "data": {
    "user_id": "uuid",
    "email": "user@example.com",
    "first_name": "John",
    "last_name": "Doe"
  }
}
```

#### user.deleted
```json
{
  "event_type": "identity.user.deleted",
  "data": {
    "user_id": "uuid",
    "email": "user@example.com",
    "deleted_at": "ISO8601"
  }
}
```

#### organization.created
```json
{
  "event_type": "identity.organization.created",
  "data": {
    "organization_id": "uuid",
    "name": "PharmaCorp",
    "slug": "pharmacorp",
    "plan": "enterprise"
  }
}
```

#### workspace.created
```json
{
  "event_type": "identity.workspace.created",
  "data": {
    "workspace_id": "uuid",
    "organization_id": "uuid",
    "name": "Oncology Research"
  }
}
```

#### project.created
```json
{
  "event_type": "identity.project.created",
  "data": {
    "project_id": "uuid",
    "workspace_id": "uuid",
    "name": "HER2 Inhibitors"
  }
}
```

---

### 2. Literature Intelligence Events

#### document.ingested
```json
{
  "event_type": "literature.document.ingested",
  "data": {
    "document_id": "uuid",
    "source": "pubmed",
    "source_document_id": "PMID12345678",
    "title": "Study Title",
    "publication_date": "ISO8601",
    "doi": "10.1234/example"
  }
}
```

#### document.processed
```json
{
  "event_type": "literature.document.processed",
  "data": {
    "document_id": "uuid",
    "processing_status": "completed",
    "entities_extracted": 25,
    "relationships_extracted": 10,
    "summary_generated": true
  }
}
```

#### entities.extracted
```json
{
  "event_type": "literature.entities.extracted",
  "data": {
    "document_id": "uuid",
    "entities": [
      {
        "entity_type": "gene",
        "entity_text": "BRCA1",
        "canonical_id": "gene:BRCA1",
        "confidence": 0.95
      }
    ]
  }
}
```

#### relationships.extracted
```json
{
  "event_type": "literature.relationships.extracted",
  "data": {
    "document_id": "uuid",
    "relationships": [
      {
        "from_entity": "gene:BRCA1",
        "to_entity": "disease:breast_cancer",
        "relationship_type": "associated_with",
        "confidence": 0.9
      }
    ]
  }
}
```

#### document.deduplicated
```json
{
  "event_type": "literature.document.deduplicated",
  "data": {
    "document_id": "uuid",
    "representative_document_id": "uuid",
    "similarity": 0.95,
    "action": "merged"
  }
}
```

#### novelty.scored
```json
{
  "event_type": "literature.novelty.scored",
  "data": {
    "document_id": "uuid",
    "novelty_score": 0.85,
    "aspects": {
      "methodology": 0.9,
      "findings": 0.8,
      "application": 0.85
    }
  }
}
```

---

### 3. Knowledge Graph Events

#### node.created
```json
{
  "event_type": "graph.node.created",
  "data": {
    "node_id": "uuid",
    "graph_id": "gene:BRCA1",
    "type": "gene",
    "labels": ["gene", "tumor_suppressor"],
    "properties": {
      "name": "BRCA1",
      "entrez_id": "672"
    }
  }
}
```

#### node.updated
```json
{
  "event_type": "graph.node.updated",
  "data": {
    "node_id": "uuid",
    "graph_id": "gene:BRCA1",
    "type": "gene",
    "properties": {
      "name": "BRCA1",
      "entrez_id": "672",
      "new_property": "value"
    },
    "version": 2
  }
}
```

#### node.deleted
```json
{
  "event_type": "graph.node.deleted",
  "data": {
    "node_id": "uuid",
    "graph_id": "gene:BRCA1",
    "type": "gene",
    "deleted_at": "ISO8601"
  }
}
```

#### relationship.created
```json
{
  "event_type": "graph.relationship.created",
  "data": {
    "relationship_id": "uuid",
    "from_node_id": "uuid",
    "to_node_id": "uuid",
    "type": "targets",
    "properties": {
      "mechanism": "inhibition",
      "confidence": 0.9
    }
  }
}
```

#### entity.resolved
```json
{
  "event_type": "graph.entity.resolved",
  "data": {
    "canonical_id": "uuid",
    "alias_ids": ["alias1", "alias2"],
    "confidence": 0.95,
    "entity_type": "gene"
  }
}
```

---

### 4. AI Orchestration Events

#### agent.invoked
```json
{
  "event_type": "ai.agent.invoked",
  "data": {
    "agent_id": "uuid",
    "agent_name": "literature-agent",
    "conversation_id": "uuid",
    "input": "Find recent HER2 publications",
    "context": {}
  }
}
```

#### agent.response
```json
{
  "event_type": "ai.agent.response",
  "data": {
    "agent_id": "uuid",
    "conversation_id": "uuid",
    "message_id": "uuid",
    "content": "Based on recent publications...",
    "tool_calls": [],
    "status": "completed"
  }
}
```

#### tool.invoked
```json
{
  "event_type": "ai.tool.invoked",
  "data": {
    "tool_id": "uuid",
    "tool_name": "search_documents",
    "conversation_id": "uuid",
    "message_id": "uuid",
    "parameters": {
      "query": "HER2 breast cancer",
      "limit": 10
    }
  }
}
```

#### tool.completed
```json
{
  "event_type": "ai.tool.completed",
  "data": {
    "tool_id": "uuid",
    "tool_name": "search_documents",
    "conversation_id": "uuid",
    "message_id": "uuid",
    "result": {},
    "status": "completed",
    "duration_ms": 1500
  }
}
```

#### conversation.created
```json
{
  "event_type": "ai.conversation.created",
  "data": {
    "conversation_id": "uuid",
    "agent_id": "uuid",
    "user_id": "uuid",
    "title": "HER2 Research"
  }
}
```

#### model.deployed
```json
{
  "event_type": "ai.model.deployed",
  "data": {
    "model_id": "uuid",
    "model_name": "biomed-llm-v1",
    "version": "v1.2.0",
    "deployment_config": {
      "replicas": 3,
      "gpu_type": "A100"
    }
  }
}
```

---

### 5. Scientific Search Events

#### document.indexed
```json
{
  "event_type": "search.document.indexed",
  "data": {
    "document_id": "uuid",
    "index": "documents",
    "indexed_at": "ISO8601"
  }
}
```

#### embedding.generated
```json
{
  "event_type": "search.embedding.generated",
  "data": {
    "document_id": "uuid",
    "model": "text-embedding-ada-002",
    "dimension": 1536,
    "generated_at": "ISO8601"
  }
}
```

#### search.performed
```json
{
  "event_type": "search.search.performed",
  "data": {
    "query": "HER2 breast cancer",
    "search_type": "hybrid",
    "results_count": 25,
    "latency_ms": 150,
    "user_id": "uuid"
  }
}
```

---

### 6. Molecule Discovery Events

#### molecule.created
```json
{
  "event_type": "molecule.molecule.created",
  "data": {
    "molecule_id": "uuid",
    "smiles": "CC(=O)OC1=CC=CC=C1C(=O)O",
    "canonical_smiles": "CC(=O)OC1=CC=CC=C1C(=O)O",
    "inchi_key": "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
    "molecular_weight": 180.16
  }
}
```

#### docking.job.submitted
```json
{
  "event_type": "molecule.docking.job.submitted",
  "data": {
    "job_id": "uuid",
    "target_id": "uuid",
    "ligand_smiles": "CC(=O)OC1=CC=CC=C1C(=O)O",
    "parameters": {
      "exhaustiveness": 8,
      "num_modes": 10
    }
  }
}
```

#### docking.job.completed
```json
{
  "event_type": "molecule.docking.job.completed",
  "data": {
    "job_id": "uuid",
    "status": "completed",
    "poses_count": 10,
    "best_score": -9.5,
    "completed_at": "ISO8601"
  }
}
```

#### admet.predicted
```json
{
  "event_type": "molecule.admet.predicted",
  "data": {
    "molecule_id": "uuid",
    "predictions": {
      "bbb_penetrant": true,
      "bbb_probability": 0.85,
      "clearance": 10.5,
      "clearance_unit": "mL/min/kg"
    }
  }
}
```

#### molecules.generated
```json
{
  "event_type": "molecule.molecules.generated",
  "data": {
    "generation_job_id": "uuid",
    "target_id": "uuid",
    "molecules_count": 100,
    "selected_count": 10,
    "generated_at": "ISO8601"
  }
}
```

---

### 7. Clinical Intelligence Events

#### clinical_trial.ingested
```json
{
  "event_type": "clinical.trial.ingested",
  "data": {
    "trial_id": "uuid",
    "nct_id": "NCT12345678",
    "title": "Study of Drug X",
    "phase": "Phase II",
    "status": "Recruiting"
  }
}
```

#### clinical_trial.updated
```json
{
  "event_type": "clinical.trial.updated",
  "data": {
    "trial_id": "uuid",
    "nct_id": "NCT12345678",
    "updated_fields": ["status", "enrollment"],
    "new_status": "Active",
    "new_enrollment": 150
  }
}
```

#### prediction.generated
```json
{
  "event_type": "clinical.prediction.generated",
  "data": {
    "trial_id": "uuid",
    "drug_id": "uuid",
    "indication": "Breast Cancer",
    "phase": "Phase II",
    "success_probability": 0.75,
    "confidence": 0.8
  }
}
```

---

### 8. Competitive Intelligence Events

#### competitor.tracked
```json
{
  "event_type": "competitor.competitor.tracked",
  "data": {
    "competitor_id": "uuid",
    "name": "CompetitorCorp",
    "industry": "Biotechnology",
    "tracked_at": "ISO8601"
  }
}
```

#### asset.tracked
```json
{
  "event_type": "competitor.asset.tracked",
  "data": {
    "asset_id": "uuid",
    "competitor_id": "uuid",
    "name": "Drug X",
    "phase": "Phase II",
    "indication": "Breast Cancer"
  }
}
```

#### event.detected
```json
{
  "event_type": "competitor.event.detected",
  "data": {
    "competitor_id": "uuid",
    "event_type": "funding",
    "title": "Series C funding round",
    "event_date": "ISO8601",
    "details": {}
  }
}
```

#### opportunity.identifed
```json
{
  "event_type": "competitor.opportunity.identified",
  "data": {
    "asset_id": "uuid",
    "company": "StartupCorp",
    "opportunity_type": "licensing",
    "attractiveness_score": 0.85,
    "rationale": "First-in-class mechanism"
  }
}
```

---

### 9. Portfolio Management Events

#### portfolio.created
```json
{
  "event_type": "portfolio.portfolio.created",
  "data": {
    "portfolio_id": "uuid",
    "workspace_id": "uuid",
    "name": "Oncology Portfolio 2024"
  }
}
```

#### asset.added
```json
{
  "event_type": "portfolio.asset.added",
  "data": {
    "asset_id": "uuid",
    "portfolio_id": "uuid",
    "name": "HER2 Inhibitor X",
    "type": "internal"
  }
}
```

#### asset.scored
```json
{
  "event_type": "portfolio.asset.scored",
  "data": {
    "asset_id": "uuid",
    "portfolio_id": "uuid",
    "composite_score": 0.82,
    "dimension_scores": {
      "scientific": 0.85,
      "commercial": 0.80,
      "technical": 0.81
    }
  }
}
```

#### portfolio.scored
```json
{
  "event_type": "portfolio.portfolio.scored",
  "data": {
    "portfolio_id": "uuid",
    "composite_score": 0.78,
    "risk_score": 0.35,
    "roi_potential": 0.85
  }
}
```

---

### 10. Collaboration Events

#### notebook.created
```json
{
  "event_type": "collaboration.notebook.created",
  "data": {
    "notebook_id": "uuid",
    "project_id": "uuid",
    "title": "HER2 Target Validation",
    "owner_id": "uuid"
  }
}
```

#### notebook.updated
```json
{
  "event_type": "collaboration.notebook.updated",
  "data": {
    "notebook_id": "uuid",
    "updated_by": "uuid",
    "changes": ["cell_added", "cell_modified"]
  }
}
```

#### cell.updated
```json
{
  "event_type": "collaboration.cell.updated",
  "data": {
    "notebook_id": "uuid",
    "cell_id": "uuid",
    "cell_type": "markdown",
    "content": "# Updated content",
    "updated_by": "uuid"
  }
}
```

#### document.uploaded
```json
{
  "event_type": "collaboration.document.uploaded",
  "data": {
    "document_id": "uuid",
    "workspace_id": "uuid",
    "name": "Research Report.pdf",
    "type": "pdf",
    "size": 1024000,
    "uploaded_by": "uuid"
  }
}
```

#### report.generated
```json
{
  "event_type": "collaboration.report.generated",
  "data": {
    "report_id": "uuid",
    "type": "scientific",
    "parameters": {},
    "generated_by": "uuid",
    "file_path": "s3://reports/report.pdf"
  }
}
```

---

## Event Flows

### 1. Literature Ingestion Flow

```
[Ingestion Service]
    ↓ document.ingested
[Extraction Service]
    ↓ entities.extracted
[Entity Resolution Service]
    ↓ entity.resolved
[Graph Service]
    ↓ node.created, relationship.created
[Graph Service]
    ↓ node.created
[Knowledge Graph]
    ↓ document.indexed
[Indexing Service]
    ↓ embedding.generated
[Inference Service]
    ↓ document.indexed
[Search Service]
    ↓ novelty.scored
[Extraction Service]
    ↓ document.processed
[Ingestion Service]
```

### 2. AI Agent Conversation Flow

```
[Agent Orchestrator]
    ↓ agent.invoked
[Agent Orchestrator]
    ↓ tool.invoked
[Tool Registry Service]
    ↓ tool.completed
[Agent Orchestrator]
    ↓ agent.response
[Agent Orchestrator]
    ↓ conversation.updated
[Agent Orchestrator]
```

### 3. Molecule Discovery Flow

```
[Molecule Service]
    ↓ molecule.created
[Generative Chemistry Service]
    ↓ molecules.generated
[Generative Chemistry Service]
    ↓ molecule.created
[Molecule Service]
    ↓ docking.job.submitted
[Docking Service]
    ↓ docking.job.completed
[Docking Service]
    ↓ admet.predicted
[ADMET Service]
    ↓ admet.predicted
[Portfolio Service]
    ↓ asset.scored
[Scoring Engine Service]
```

### 4. Clinical Intelligence Flow

```
[Clinical Trial Service]
    ↓ clinical_trial.ingested
[Clinical Trial Service]
    ↓ clinical_trial.updated
[Clinical Trial Service]
    ↓ prediction.generated
[Clinical Prediction Service]
    ↓ asset.scored
[Scoring Engine Service]
    ↓ portfolio.scored
[Portfolio Service]
```

### 5. Competitive Intelligence Flow

```
[Competitor Service]
    ↓ competitor.tracked
[Competitor Service]
    ↓ asset.tracked
[Competitor Service]
    ↓ event.detected
[Competitor Service]
    ↓ opportunity.identified
[Market Intelligence Service]
    ↓ asset.added
[Portfolio Service]
```

---

## Topic Configuration

### Topic List

| Topic | Partitions | Retention | Replication | Purpose |
|-------|-----------|-----------|-------------|---------|
| identity.user.created | 3 | 7d | 3 | User creation events |
| identity.user.deleted | 3 | 30d | 3 | User deletion events |
| identity.organization.created | 3 | 7d | 3 | Organization creation |
| identity.workspace.created | 3 | 7d | 3 | Workspace creation |
| identity.project.created | 3 | 7d | 3 | Project creation |
| literature.document.ingested | 12 | 7d | 3 | Document ingestion |
| literature.document.processed | 12 | 7d | 3 | Document processing |
| literature.entities.extracted | 12 | 7d | 3 | Entity extraction |
| literature.relationships.extracted | 12 | 7d | 3 | Relationship extraction |
| literature.novelty.scored | 12 | 7d | 3 | Novelty scoring |
| graph.node.created | 12 | 7d | 3 | Node creation |
| graph.node.updated | 12 | 7d | 3 | Node updates |
| graph.relationship.created | 12 | 7d | 3 | Relationship creation |
| graph.entity.resolved | 12 | 7d | 3 | Entity resolution |
| ai.agent.invoked | 12 | 7d | 3 | Agent invocation |
| ai.agent.response | 12 | 7d | 3 | Agent response |
| ai.tool.invoked | 12 | 7d | 3 | Tool invocation |
| ai.tool.completed | 12 | 7d | 3 | Tool completion |
| ai.model.deployed | 3 | 7d | 3 | Model deployment |
| search.document.indexed | 12 | 7d | 3 | Document indexing |
| search.embedding.generated | 12 | 7d | 3 | Embedding generation |
| search.search.performed | 12 | 1d | 3 | Search analytics |
| molecule.molecule.created | 6 | 7d | 3 | Molecule creation |
| molecule.docking.job.submitted | 6 | 7d | 3 | Docking job submission |
| molecule.docking.job.completed | 6 | 7d | 3 | Docking job completion |
| molecule.admet.predicted | 6 | 7d | 3 | ADMET prediction |
| molecule.molecules.generated | 6 | 7d | 3 | Molecule generation |
| clinical.trial.ingested | 6 | 7d | 3 | Clinical trial ingestion |
| clinical.trial.updated | 6 | 7d | 3 | Clinical trial updates |
| clinical.prediction.generated | 6 | 7d | 3 | Clinical prediction |
| competitor.competitor.tracked | 3 | 7d | 3 | Competitor tracking |
| competitor.asset.tracked | 3 | 7d | 3 | Asset tracking |
| competitor.event.detected | 3 | 7d | 3 | Event detection |
| competitor.opportunity.identified | 3 | 7d | 3 | Opportunity identification |
| portfolio.portfolio.created | 3 | 7d | 3 | Portfolio creation |
| portfolio.asset.added | 3 | 7d | 3 | Asset addition |
| portfolio.asset.scored | 3 | 7d | 3 | Asset scoring |
| portfolio.portfolio.scored | 3 | 7d | 3 | Portfolio scoring |
| collaboration.notebook.created | 6 | 7d | 3 | Notebook creation |
| collaboration.notebook.updated | 6 | 7d | 3 | Notebook updates |
| collaboration.cell.updated | 6 | 7d | 3 | Cell updates |
| collaboration.document.uploaded | 6 | 7d | 3 | Document upload |
| collaboration.report.generated | 3 | 7d | 3 | Report generation |

---

## Consumer Groups

### Consumer Group Strategy

Each service has its own consumer group for independent processing. For parallel processing within a service, consumer group members share the load.

### Consumer Groups

| Consumer Group | Topics | Members | Purpose |
|----------------|--------|----------|---------|
| extraction-service | literature.document.ingested | 4 | Process documents |
| entity-resolution-service | literature.entities.extracted | 2 | Resolve entities |
| graph-service | graph.entity.resolved | 2 | Update graph |
| indexing-service | graph.node.created, graph.relationship.created | 4 | Index content |
| embedding-service | document.indexed | 4 | Generate embeddings |
| agent-orchestrator | ai.agent.invoked, ai.tool.completed | 6 | Orchestrate agents |
| docking-service | molecule.docking.job.submitted | 4 | Process docking |
| admet-service | molecule.created | 4 | Predict ADMET |
| clinical-prediction-service | clinical.trial.ingested | 2 | Generate predictions |
| scoring-engine-service | asset.added, clinical.prediction.generated | 2 | Score assets |
| search-analytics | search.search.performed | 2 | Analytics |

---

## Event Ordering Guarantees

### Key-Based Ordering
Events with the same key are guaranteed to be processed in order:
- `document_id` for literature events
- `node_id` for graph events
- `conversation_id` for agent events
- `molecule_id` for molecule events

### Partitioning Strategy
- Hash partitioning on entity ID for ordering
- Round-robin for independent events
- Custom partitioners for specific use cases

---

## Dead Letter Queue (DLQ)

### DLQ Topics
Each topic has a corresponding DLQ topic:
- `{topic}.dlq`

### DLQ Handling
- Failed messages sent to DLQ after 3 retry attempts
- DLQ monitored by observability service
- Manual replay mechanism for DLQ messages
- Alert on DLQ size threshold

---

## Event Schema Registry

### Schema Management
- Confluent Schema Registry for Avro/JSON schemas
- Schema evolution with backward compatibility
- Schema versioning
- Schema validation at producer/consumer

### Schema Storage
- Schemas stored in Git repository
- Schema changes via pull requests
- Automated schema compatibility checks

---

## Event Testing

### Event Contract Tests
- Validate event schema
- Validate required fields
- Validate data types
- Validate metadata

### Integration Tests
- End-to-end event flow tests
- Consumer group tests
- DLQ tests
- Replay tests

---

## Event Monitoring

### Metrics
- Event production rate per topic
- Event consumption lag per consumer group
- Error rate per consumer
- DLQ size per topic

### Alerts
- High consumer lag (> 10 minutes)
- High error rate (> 5%)
- DLQ size threshold (> 1000 messages)
- Consumer group offline

---

## Event Security

### Authentication
- SASL/SCRAM for client authentication
- mTLS for inter-service communication

### Authorization
- ACLs per topic
- Producer/consumer permissions
- Service-based authentication

### Encryption
- TLS for data in transit
- Encryption at rest (Kafka broker)

---

## Event Replay

### Replay Strategy
- Replay from specific timestamp
- Replay to specific consumer group
- Replay with rate limiting
- Replay with filtering

### Use Cases
- Data recovery
- Bug fix verification
- Feature testing
- Analytics reprocessing

---

## Event Versioning

### Versioning Strategy
- Event version in event type: `{event_type}.v{version}`
- Backward compatibility for minor versions
- Breaking changes require new event type
- Deprecation timeline for old versions

### Migration Path
- Dual-write old and new versions during migration
- Consumers updated to handle both versions
- Old version deprecated after migration complete
