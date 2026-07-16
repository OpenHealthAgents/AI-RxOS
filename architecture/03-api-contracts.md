# API Contracts - AI-RxOS

## Overview
AI-RxOS exposes APIs through three protocols:
- **REST APIs**: Public-facing, web client, mobile client
- **GraphQL**: Complex queries, data federation, BFF
- **gRPC**: High-performance inter-service communication

All APIs follow OpenAPI 3.0 specification for REST and Protocol Buffers for gRPC.

---

## API Gateway Configuration

### Base URLs
- **Production**: `https://api.ai-rxos.com`
- **Staging**: `https://api-staging.ai-rxos.com`
- **Development**: `http://localhost:8080`

### API Versioning
- URL-based versioning: `/api/v1/`, `/api/v2/`
- Header-based versioning: `API-Version: v1`

### Authentication
- Bearer token: `Authorization: Bearer <jwt_token>`
- API key: `X-API-Key: <api_key>`
- Session cookie: For web clients

### Rate Limiting
- Free tier: 100 requests/minute
- Enterprise: 10,000 requests/minute
- Burst: 2x sustained rate

---

## 1. Identity & Access APIs (better-auth)

### 1.1 Auth Service (REST - better-auth endpoints)

#### Authentication Endpoints

**POST /api/v1/auth/sign-in/email**
```json
{
  "email": "user@example.com",
  "password": "password"
}
```
Response:
```json
{
  "user": {
    "id": "user-id",
    "email": "user@example.com",
    "name": "John Doe"
  },
  "session": {
    "token": "session-token",
    "expiresAt": "2024-01-01T00:00:00Z"
  }
}
```

**POST /api/v1/auth/sign-in/oauth**
Query params: `provider` (google, github, etc.)
Redirects to OAuth provider

**GET /api/v1/auth/callback/oauth**
Query params: `provider`, `code`, `state`
Response: Redirects with session token

**POST /api/v1/auth/sign-up/email**
```json
{
  "email": "user@example.com",
  "password": "password",
  "name": "John Doe"
}
```

**POST /api/v1/auth/sign-in/passkey**
```json
{
  "email": "user@example.com"
}
```
Response:
```json
{
  "options": {
    "challenge": "base64-challenge",
    "allowCredentials": [...]
  }
}
```

**POST /api/v1/auth/verify-passkey**
```json
{
  "credentialId": "credential-id",
  "authenticatorData": "base64",
  "clientDataJSON": "base64",
  "signature": "base64"
}
```

**POST /api/v1/auth/sign-out**
Headers: `Authorization: Bearer <session-token>`

**GET /api/v1/auth/session**
Headers: `Authorization: Bearer <session-token>`
Response:
```json
{
  "user": {
    "id": "user-id",
    "email": "user@example.com",
    "name": "John Doe"
  },
  "session": {
    "token": "session-token",
    "expiresAt": "2024-01-01T00:00:00Z"
  }
}
```

#### 2FA Endpoints

**POST /api/v1/auth/2fa/enable**
Headers: `Authorization: Bearer <session-token>`
```json
{
  "password": "current-password"
}
```
Response:
```json
{
  "secret": "JBSWY3DPEHPK3PXP",
  "qrCode": "data:image/png;base64,...",
  "backupCodes": ["code1", "code2", ...]
}
```

**POST /api/v1/auth/2fa/verify**
```json
{
  "code": "123456"
}
```

**POST /api/v1/auth/2fa/disable**
Headers: `Authorization: Bearer <session-token>`
```json
{
  "code": "123456"
}
```

#### Account Linking Endpoints

**POST /api/v1/auth/link-account**
```json
{
  "provider": "google",
  "code": "oauth-code"
}
```

**DELETE /api/v1/auth/unlink-account**
```json
{
  "accountId": "account-id"
}
```

#### Organization Endpoints

**GET /api/v1/organizations**
Headers: `Authorization: Bearer <session-token>`
Response:
```json
{
  "organizations": [
    {
      "id": "org-id",
      "name": "PharmaCorp",
      "slug": "pharmacorp",
      "role": "admin",
      "createdAt": "2024-01-01T00:00:00Z"
    }
  ]
}
```

**POST /api/v1/organizations**
```json
{
  "name": "PharmaCorp",
  "slug": "pharmacorp"
}
```

**GET /api/v1/organizations/{org_id}/members**
Response:
```json
{
  "members": [
    {
      "userId": "user-id",
      "name": "John Doe",
      "email": "user@example.com",
      "role": "admin",
      "joinedAt": "2024-01-01T00:00:00Z"
    }
  ]
}
```

**POST /api/v1/organizations/{org_id}/members/invite**
```json
{
  "email": "newuser@example.com",
  "role": "member"
}
```

**PUT /api/v1/organizations/{org_id}/members/{user_id}/role**
```json
{
  "role": "admin"
}
```

**DELETE /api/v1/organizations/{org_id}/members/{user_id}**

#### API Key Endpoints

**POST /api/v1/api-keys**
```json
{
  "name": "Service Account Key",
  "organizationId": "org-id",
  "scopes": ["read", "write"]
}
```
Response:
```json
{
  "id": "key-id",
  "key": "sk_live_...",
  "name": "Service Account Key",
  "createdAt": "2024-01-01T00:00:00Z"
}
```

**GET /api/v1/api-keys**
Response:
```json
{
  "apiKeys": [
    {
      "id": "key-id",
      "name": "Service Account Key",
      "prefix": "sk_live_",
      "lastUsedAt": "2024-01-01T00:00:00Z",
      "createdAt": "2024-01-01T00:00:00Z"
    }
  ]
}
```

**DELETE /api/v1/api-keys/{key_id}**

**POST /api/v1/api-keys/{key_id}/rotate**
Response:
```json
{
  "key": "sk_live_new_..."
}
```

### 1.2 Auth Service Token Validation (Local JWKS)

Instead of making synchronous gRPC calls to validate user sessions or API keys, downstream microservices perform local JWT validation. The Auth Service acts as an OIDC/OAuth2 identity provider and exposes a public JSON Web Key Set (JWKS) endpoint. Microservices cache these public keys to verify the signature of JWT tokens locally.

#### JWKS Endpoint
**GET /api/v1/auth/jwks**

Response:
```json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "auth-key-v1",
      "use": "sig",
      "alg": "RS256",
      "n": "u1W_Oi5...",
      "e": "AQAB"
    }
  ]
}
```

#### JWT Claims Schema
The JWT tokens issued by the Better Auth service contain the following standard and custom claims:
```json
{
  "iss": "https://auth.ai-rxos.local",
  "sub": "user-uuid",
  "aud": "https://api.ai-rxos.local",
  "exp": 1719878400,
  "nbf": 1719874800,
  "iat": 1719874800,
  "jti": "jwt-uuid",
  "user": {
    "name": "John Doe",
    "email": "user@example.com"
  },
  "organization_id": "org-uuid",
  "workspace_id": "workspace-uuid",
  "project_id": "project-uuid",
  "roles": ["member"],
  "scopes": ["read:notebooks", "write:notebooks"]
}
```

### 1.3 Organization Service (REST - Workspace and Project Management)

**GET /api/v1/organizations/{org_id}/workspaces**
Headers: `Authorization: Bearer <session-token>`

**POST /api/v1/organizations/{org_id}/workspaces**
```json
{
  "name": "Oncology Research",
  "description": "Oncology drug discovery workspace"
}
```

**GET /api/v1/workspaces/{workspace_id}/projects**

**POST /api/v1/workspaces/{workspace_id}/projects**
```json
{
  "name": "HER2 Inhibitors",
  "description": "HER2-targeted therapy project"
}
```

---

## 2. Knowledge Graph APIs

### 2.1 Graph Service (GraphQL)

```graphql
type Query {
  node(id: ID!): Node
  nodes(ids: [ID!]!): [Node]
  searchNodes(query: String!, types: [NodeType!], limit: Int): [Node]
  
  relationship(id: ID!): Relationship
  relationships(from: ID, to: ID, type: String): [Relationship]
  
  path(from: ID!, to: ID!, maxDepth: Int): [Path]
  
  cypher(query: String!, params: Map): CypherResult
}

type Mutation {
  createNode(input: NodeInput!): Node
  updateNode(id: ID!, input: NodeInput!): Node
  deleteNode(id: ID!): Boolean
  
  createRelationship(input: RelationshipInput!): Relationship
  updateRelationship(id: ID!, input: RelationshipInput!): Relationship
  deleteRelationship(id: ID!): Boolean
}

type Node {
  id: ID!
  type: NodeType!
  properties: Map
  labels: [String!]
  created_at: DateTime
  updated_at: DateTime
}

type Relationship {
  id: ID!
  type: String!
  from: Node!
  to: Node!
  properties: Map
  evidence: [Evidence!]
  confidence: Float
  created_at: DateTime
  updated_at: DateTime
}

type Evidence {
  id: ID!
  source: String!
  source_id: String!
  url: String
  confidence: Float
}

enum NodeType {
  GENE
  PROTEIN
  DISEASE
  DRUG
  TARGET
  COMPANY
  PUBLICATION
  PATENT
  CLINICAL_TRIAL
  CONFERENCE
  BIOMARKER
  PATHWAY
  MUTATION
}

type Path {
  nodes: [Node!]!
  relationships: [Relationship!]!
  length: Int!
}

type CypherResult {
  columns: [String!]!
  data: [[Any!]!]!
}
```

---

### 2.2 Entity Resolution Service (gRPC)

```protobuf
service EntityResolutionService {
  rpc ResolveEntity(ResolveEntityRequest) returns (ResolvedEntity);
  rpc ResolveEntities(ResolveEntitiesRequest) returns (ResolvedEntities);
  rpc FindDuplicates(FindDuplicatesRequest) returns (FindDuplicatesResponse);
  rpc MergeEntities(MergeEntitiesRequest) returns (google.protobuf.Empty);
}

message ResolveEntityRequest {
  string type = 1;
  map<string, string> attributes = 2;
}

message ResolvedEntity {
  string canonical_id = 1;
  repeated string alias_ids = 2;
  float confidence = 3;
  Entity entity = 4;
}

message Entity {
  string id = 1;
  string type = 2;
  map<string, string> attributes = 3;
}

message ResolveEntitiesRequest {
  repeated ResolveEntityRequest entities = 1;
}

message ResolvedEntities {
  repeated ResolvedEntity entities = 1;
}

message FindDuplicatesRequest {
  string type = 1;
  string entity_id = 2;
  float threshold = 3;
}

message FindDuplicatesResponse {
  repeated DuplicateGroup groups = 1;
}

message DuplicateGroup {
  repeated string entity_ids = 1;
  float similarity = 2;
}

message MergeEntitiesRequest {
  string canonical_id = 1;
  repeated string alias_ids = 2;
}
```

---

## 3. Literature Intelligence APIs

### 3.1 Ingestion Service (REST)

**GET /api/v1/ingestion/sources**
Response:
```json
{
  "sources": [
    {
      "id": "pubmed",
      "name": "PubMed",
      "type": "literature",
      "enabled": true,
      "last_sync": "2024-01-01T00:00:00Z"
    },
    {
      "id": "biorxiv",
      "name": "bioRxiv",
      "type": "preprint",
      "enabled": true,
      "last_sync": "2024-01-01T00:00:00Z"
    }
  ]
}
```

**POST /api/v1/ingestion/jobs**
```json
{
  "source_id": "pubmed",
  "query": "HER2 AND breast cancer",
  "schedule": "0 0 * * *"
}
```

**GET /api/v1/ingestion/jobs/{job_id}**

**POST /api/v1/ingestion/jobs/{job_id}/trigger**

---

### 3.2 Extraction Service (gRPC)

```protobuf
service ExtractionService {
  rpc ExtractEntities(ExtractEntitiesRequest) returns (ExtractEntitiesResponse);
  rpc ExtractRelationships(ExtractRelationshipsRequest) returns (ExtractRelationshipsResponse);
  rpc Summarize(SummarizeRequest) returns (SummarizeResponse);
  rpc DetectDuplicates(DetectDuplicatesRequest) returns (DetectDuplicatesResponse);
  rpc ScoreNovelty(ScoreNoveltyRequest) returns (ScoreNoveltyResponse);
}

message ExtractEntitiesRequest {
  string document_id = 1;
  string text = 2;
  repeated EntityType types = 3;
}

message EntityType {
  string name = 1;
  repeated string labels = 2;
}

message ExtractEntitiesResponse {
  repeated Entity entities = 1;
  repeated ExtractionMetadata metadata = 2;
}

message Entity {
  string text = 1;
  string type = 2;
  string canonical_id = 3;
  float confidence = 4;
  int32 start = 5;
  int32 end = 6;
}

message ExtractionMetadata {
  string model = 1;
  float confidence = 2;
  google.protobuf.Timestamp extracted_at = 3;
}

message ExtractRelationshipsRequest {
  string document_id = 1;
  repeated Entity entities = 2;
  string text = 3;
}

message ExtractRelationshipsResponse {
  repeated Relationship relationships = 1;
}

message Relationship {
  string from_entity = 1;
  string to_entity = 2;
  string type = 3;
  float confidence = 4;
  string evidence = 5;
}

message SummarizeRequest {
  string document_id = 1;
  string text = 2;
  int32 max_length = 3;
}

message SummarizeResponse {
  string summary = 1;
  repeated string key_points = 2;
  float confidence = 3;
}

message DetectDuplicatesRequest {
  repeated string document_ids = 1;
}

message DetectDuplicatesResponse {
  repeated DuplicateGroup groups = 1;
}

message DuplicateGroup {
  repeated string document_ids = 1;
  float similarity = 2;
  string reason = 3;
}

message ScoreNoveltyRequest {
  string document_id = 1;
  string text = 2;
  repeated string related_documents = 3;
}

message ScoreNoveltyResponse {
  float novelty_score = 1;
  repeated NoveltyAspect aspects = 2;
}

message NoveltyAspect {
  string aspect = 1;
  float score = 2;
  string explanation = 3;
}
```

---

## 4. AI Orchestration APIs

### 4.1 Agent Orchestrator Service (gRPC)

```protobuf
service AgentOrchestrator {
  rpc InvokeAgent(InvokeAgentRequest) returns (stream AgentResponse);
  rpc CreateConversation(CreateConversationRequest) returns (Conversation);
  rpc SendMessage(SendMessageRequest) returns (stream MessageResponse);
  rpc GetConversation(GetConversationRequest) returns (Conversation);
  rpc ListConversations(ListConversationsRequest) returns (ListConversationsResponse);
  rpc ExecuteTool(ExecuteToolRequest) returns (stream ToolResponse);
}

message InvokeAgentRequest {
  string agent_id = 1;
  string input = 2;
  map<string, string> context = 3;
  string conversation_id = 4;
}

message AgentResponse {
  string content = 1;
  repeated ToolCall tool_calls = 2;
  string status = 3; // in_progress, completed, error
  string error_message = 4;
  map<string, string> metadata = 5;
}

message ToolCall {
  string tool_id = 1;
  string tool_name = 2;
  map<string, string> parameters = 3;
}

message CreateConversationRequest {
  string agent_id = 1;
  string title = 2;
  map<string, string> metadata = 3;
}

message Conversation {
  string id = 1;
  string agent_id = 2;
  string title = 3;
  repeated Message messages = 4;
  google.protobuf.Timestamp created_at = 5;
  google.protobuf.Timestamp updated_at = 6;
}

message Message {
  string id = 1;
  string role = 2; // user, assistant, system, tool
  string content = 3;
  repeated ToolCall tool_calls = 4;
  google.protobuf.Timestamp created_at = 5;
}

message SendMessageRequest {
  string conversation_id = 1;
  string content = 2;
  map<string, string> context = 3;
}

message MessageResponse {
  Message message = 1;
  repeated ToolCall tool_calls = 2;
}

message GetConversationRequest {
  string conversation_id = 1;
}

message ListConversationsRequest {
  string agent_id = 1;
  int32 page = 2;
  int32 limit = 3;
}

message ListConversationsResponse {
  repeated Conversation conversations = 1;
  int32 total = 2;
}

message ExecuteToolRequest {
  string tool_id = 1;
  map<string, string> parameters = 2;
  string conversation_id = 3;
}

message ToolResponse {
  string result = 1;
  string status = 2; // in_progress, completed, error
  string error_message = 3;
}
```

---

### 4.2 Model Registry Service (REST)

**GET /api/v1/models**
Query params: `type`, `framework`, `status`

Response:
```json
{
  "models": [
    {
      "id": "model-uuid",
      "name": "biomed-llm-v1",
      "type": "llm",
      "framework": "pytorch",
      "status": "deployed",
      "latest_version": "v1.2.0",
      "created_at": "2024-01-01T00:00:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "limit": 20
}
```

**POST /api/v1/models**
```json
{
  "name": "biomed-llm-v2",
  "type": "llm",
  "framework": "pytorch",
  "description": "Biomedical language model"
}
```

**GET /api/v1/models/{model_id}/versions**

**POST /api/v1/models/{model_id}/versions**
```json
{
  "version": "v1.0.0",
  "artifact_uri": "s3://models/biomed-llm-v1.0.0.pt",
  "config": {
    "parameters": {
      "max_tokens": 4096,
      "temperature": 0.7
    }
  }
}
```

**POST /api/v1/models/{model_id}/deploy**
```json
{
  "version": "v1.0.0",
  "replicas": 3,
  "gpu_type": "A100"
}
```

---

### 4.3 Inference Service (gRPC)

```protobuf
service InferenceService {
  rpc GenerateText(GenerateTextRequest) returns (stream GenerateTextResponse);
  rpc GenerateEmbedding(GenerateEmbeddingRequest) returns (GenerateEmbeddingResponse);
  rpc BatchGenerateText(BatchGenerateTextRequest) returns (stream BatchGenerateTextResponse);
  rpc BatchGenerateEmbedding(BatchGenerateEmbeddingRequest) returns (BatchGenerateEmbeddingResponse);
}

message GenerateTextRequest {
  string model_id = 1;
  string prompt = 2;
  int32 max_tokens = 3;
  float temperature = 4;
  repeated string stop_sequences = 5;
  map<string, string> parameters = 6;
}

message GenerateTextResponse {
  string text = 1;
  int32 tokens_generated = 2;
  bool finished = 3;
  string finish_reason = 4;
}

message GenerateEmbeddingRequest {
  string model_id = 1;
  repeated string texts = 2;
}

message GenerateEmbeddingResponse {
  repeated Embedding embeddings = 1;
}

message Embedding {
  string text = 1;
  repeated float vector = 2;
  int32 dimension = 3;
}

message BatchGenerateTextRequest {
  string model_id = 1;
  repeated string prompts = 2;
  int32 max_tokens = 3;
  float temperature = 4;
}

message BatchGenerateTextResponse {
  repeated GenerateTextResponse responses = 1;
  int32 batch_index = 2;
}

message BatchGenerateEmbeddingRequest {
  string model_id = 1;
  repeated string texts = 2;
}

message BatchGenerateEmbeddingResponse {
  repeated GenerateEmbeddingResponse responses = 1;
}
```

---

## 5. Scientific Search APIs

### 5.1 Search Service (GraphQL)

```graphql
type Query {
  search(
    query: String!
    filters: SearchFilters
    limit: Int
    offset: Int
  ): SearchResult
  
  semanticSearch(
    query: String!
    limit: Int
    threshold: Float
  ): [SemanticResult]
  
  hybridSearch(
    query: String!
    keywordWeight: Float
    semanticWeight: Float
    limit: Int
  ): SearchResult
}

input SearchFilters {
  types: [String!]
  dateRange: DateRange
  authors: [String!]
  journals: [String!]
  minConfidence: Float
}

input DateRange {
  from: DateTime
  to: DateTime
}

type SearchResult {
  total: Int!
  results: [SearchResultItem!]!
  aggregations: [Aggregation!]
}

type SearchResultItem {
  id: ID!
  type: String!
  title: String!
  snippet: String!
  score: Float!
  highlight: [String!]
  metadata: Map
}

type SemanticResult {
  id: ID!
  text: String!
  similarity: Float!
  metadata: Map
}

type Aggregation {
  name: String!
  buckets: [AggregationBucket!]!
}

type AggregationBucket {
  key: String!
  count: Int!
}
```

---

### 5.2 OKF Compiler Service (gRPC)

```protobuf
service CompilerService {
  rpc CompileConcept(CompileConceptRequest) returns (CompileConceptResponse);
  rpc BatchCompile(BatchCompileRequest) returns (BatchCompileResponse);
  rpc LintWiki(LintWikiRequest) returns (LintWikiResponse);
  rpc RebuildSearchIndex(RebuildSearchIndexRequest) returns (stream RebuildProgress);
}

message CompileConceptRequest {
  string concept_path = 1;      // e.g. "sales/tables/orders"
  string type = 2;              // e.g. "BigQuery Table"
  string title = 3;             // e.g. "Orders"
  string description = 4;       // e.g. "One row per completed order..."
  string resource = 5;          // e.g. URL
  repeated string tags = 6;
  string body_markdown = 7;     // Detailed schema, joins, or scientific content
}

message CompileConceptResponse {
  string file_path = 1;         // Generated markdown path
  bool success = 2;
  string error = 3;
}

message BatchCompileRequest {
  repeated CompileConceptRequest concepts = 1;
}

message BatchCompileResponse {
  int32 succeeded = 1;
  int32 failed = 2;
  repeated string errors = 3;
}

message LintWikiRequest {
  bool fix_links = 1;
}

message LintWikiResponse {
  repeated string broken_links = 1;
  repeated string contradictions = 2;
  repeated string orphans = 3;
}

message RebuildSearchIndexRequest {
  bool force_rebuild = 1;
}

message RebuildProgress {
  int32 concepts_processed = 1;
  int32 total_concepts = 2;
  float progress = 3;
  string status = 4;
}
```

---

## 6. Molecule Discovery APIs

### 6.1 Molecule Service (REST)

**GET /api/v1/molecules**
Query params: `search`, `similarity`, `substructure`, `limit`

Response:
```json
{
  "molecules": [
    {
      "id": "mol-uuid",
      "smiles": "CC(=O)OC1=CC=CC=C1C(=O)O",
      "inchi": "InChI=...",
      "inchi_key": "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
      "molecular_weight": 180.16,
      "formula": "C9H8O4",
      "created_at": "2024-01-01T00:00:00Z"
    }
  ],
  "total": 1,
  "limit": 20
}
```

**POST /api/v1/molecules**
```json
{
  "smiles": "CC(=O)OC1=CC=CC=C1C(=O)O",
  "name": "Aspirin"
}
```

**POST /api/v1/molecules/search/similarity**
```json
{
  "smiles": "CC(=O)OC1=CC=CC=C1C(=O)O",
  "threshold": 0.7,
  "limit": 10
}
```

**POST /api/v1/molecules/search/substructure**
```json
{
  "smiles": "c1ccccc1",
  "limit": 10
}
```

**GET /api/v1/molecules/{molecule_id}/properties**
Response:
```json
{
  "molecular_weight": 180.16,
  "logp": 1.19,
  "tpsa": 63.6,
  "hbd": 1,
  "hba": 4,
  "rotatable_bonds": 4,
  "aromatic_rings": 1
}
```

---

### 6.2 Docking Service (gRPC)

```protobuf
service DockingService {
  rpc Dock(DockRequest) returns (stream DockResponse);
  rpc BatchDock(BatchDockRequest) returns (stream BatchDockResponse);
  rpc GetDockingResult(GetDockingResultRequest) returns (DockingResult);
}

message DockRequest {
  string target_id = 1;
  string ligand_smiles = 2;
  string protein_structure = 3; // PDB file or ID
  DockingParameters parameters = 4;
}

message DockingParameters {
  int32 exhaustiveness = 1;
  int32 num_modes = 2;
  float energy_range = 3;
  string scoring_function = 4;
}

message DockResponse {
  string job_id = 1;
  string status = 2; // queued, running, completed, failed
  float progress = 3;
  DockingResult result = 4;
  string error = 5;
}

message DockingResult {
  string job_id = 1;
  repeated DockingPose poses = 2;
  google.protobuf.Timestamp completed_at = 3;
}

message DockingPose {
  int32 rank = 1;
  float score = 2;
  float rmsd = 3;
  string pose_data = 4; // Coordinates
  repeated Interaction interactions = 5;
}

message Interaction {
  string residue = 1;
  string type = 2; // hydrogen_bond, pi_pi, etc.
  float distance = 3;
}

message BatchDockRequest {
  string target_id = 1;
  repeated string ligand_smiles = 2;
  string protein_structure = 3;
  DockingParameters parameters = 4;
}

message BatchDockResponse {
  string job_id = 1;
  int32 completed = 2;
  int32 total = 3;
  repeated DockingResult results = 4;
}

message GetDockingResultRequest {
  string job_id = 1;
}
```

---

### 6.3 ADMET Service (gRPC)

```protobuf
service ADMETService {
  rpc PredictADMET(PredictADMETRequest) returns (PredictADMETResponse);
  rpc BatchPredictADMET(BatchPredictADMETRequest) returns (BatchPredictADMETResponse);
  rpc PredictBBB(PredictBBBRequest) returns (PredictBBBResponse);
  rpc PredictPK(PredictPKRequest) returns (PredictPKResponse);
}

message PredictADMETRequest {
  string smiles = 1;
  repeated string properties = 2;
}

message PredictADMETResponse {
  string smiles = 1;
  map<string, PropertyPrediction> predictions = 2;
}

message PropertyPrediction {
  string property = 1;
  float value = 2;
  string unit = 3;
  float confidence = 4;
  string prediction_class = 5; // high, medium, low
}

message BatchPredictADMETRequest {
  repeated string smiles = 1;
  repeated string properties = 2;
}

message BatchPredictADMETResponse {
  repeated PredictADMETResponse predictions = 1;
}

message PredictBBBRequest {
  string smiles = 1;
}

message PredictBBBResponse {
  string smiles = 1;
  bool bbb_penetrant = 2;
  float probability = 3;
  float confidence = 4;
  string explanation = 5;
}

message PredictPKRequest {
  string smiles = 1;
}

message PredictPKResponse {
  string smiles = 1;
  PKProperties pk = 2;
}

message PKProperties {
  float clearance = 1;
  string clearance_unit = 2;
  float volume_of_distribution = 3;
  string vd_unit = 4;
  float half_life = 5;
  string half_life_unit = 6;
  float bioavailability = 7;
}
```

---

## 7. Clinical Intelligence APIs

### 7.1 Clinical Trial Service (REST)

**GET /api/v1/trials**
Query params: `phase`, `indication`, `status`, `sponsor`

Response:
```json
{
  "trials": [
    {
      "id": "trial-uuid",
      "nct_id": "NCT12345678",
      "title": "A Study of Drug X in Breast Cancer",
      "phase": "Phase II",
      "indication": "Breast Cancer",
      "status": "Recruiting",
      "sponsor": "PharmaCorp",
      "start_date": "2024-01-01",
      "completion_date": "2026-12-31"
    }
  ],
  "total": 1,
  "page": 1,
  "limit": 20
}
```

**GET /api/v1/trials/{trial_id}**

**GET /api/v1/trials/{trial_id}/endpoints**

**GET /api/v1/trials/{trial_id}/biomarkers**

---

### 7.2 Clinical Prediction Service (gRPC)

```protobuf
service ClinicalPredictionService {
  rpc PredictPhaseSuccess(PredictPhaseSuccessRequest) returns (PredictPhaseSuccessResponse);
  rpc PredictApprovalProbability(PredictApprovalProbabilityRequest) returns (PredictApprovalProbabilityResponse);
  rpc PredictIndicationExpansion(PredictIndicationExpansionRequest) returns (PredictIndicationExpansionResponse);
}

message PredictPhaseSuccessRequest {
  string drug_id = 1;
  string indication = 2;
  string phase = 3;
  repeated ClinicalFeature features = 4;
}

message ClinicalFeature {
  string name = 1;
  string value = 2;
  string type = 3; // categorical, numerical
}

message PredictPhaseSuccessResponse {
  string drug_id = 1;
  string indication = 2;
  string phase = 3;
  float success_probability = 4;
  float confidence = 5;
  repeated ContributingFactor factors = 6;
}

message ContributingFactor {
  string factor = 1;
  float impact = 2;
  string explanation = 3;
}

message PredictApprovalProbabilityRequest {
  string drug_id = 1;
  string indication = 2;
  repeated ClinicalFeature features = 3;
}

message PredictApprovalProbabilityResponse {
  string drug_id = 1;
  string indication = 2;
  float approval_probability = 3;
  float confidence = 4;
  repeated PhaseProbability phase_probabilities = 5;
}

message PhaseProbability {
  string phase = 1;
  float probability = 2;
}

message PredictIndicationExpansionRequest {
  string drug_id = 1;
  string current_indication = 2;
}

message PredictIndicationExpansionResponse {
  string drug_id = 1;
  repeated IndicationOpportunity opportunities = 3;
}

message IndicationOpportunity {
  string indication = 1;
  float probability = 2;
  float market_size = 3;
  string rationale = 4;
}
```

---

## 8. Competitive Intelligence APIs

### 8.1 Competitor Service (REST)

**GET /api/v1/competitors**
Query params: `industry`, `focus_area`

Response:
```json
{
  "competitors": [
    {
      "id": "comp-uuid",
      "name": "CompetitorCorp",
      "industry": "Biotechnology",
      "focus_areas": ["Oncology", "Immunology"],
      "website": "https://competitor.com",
      "funding_stage": "Series C"
    }
  ],
  "total": 1,
  "page": 1,
  "limit": 20
}
```

**GET /api/v1/competitors/{competitor_id}/pipeline**

**GET /api/v1/competitors/{competitor_id}/assets**

---

### 8.2 Market Intelligence Service (gRPC)

```protobuf
service MarketIntelligenceService {
  rpc GenerateMarketMap(GenerateMarketMapRequest) returns (MarketMap);
  rpc AnalyzeTechnologyLandscape(AnalyzeTechnologyLandscapeRequest) returns (TechnologyLandscape);
  rpc IdentifyThreats(IdentifyThreatsRequest) returns (ThreatAnalysis);
  rpc IdentifyLicensingOpportunities(IdentifyLicensingOpportunitiesRequest) returns (LicensingOpportunities);
}

message GenerateMarketMapRequest {
  string indication = 1;
  string modality = 2;
  string mechanism = 3;
}

message MarketMap {
  string indication = 1;
  repeated MarketSegment segments = 2;
  repeated CompetitorPosition competitors = 3;
  google.protobuf.Timestamp generated_at = 4;
}

message MarketSegment {
  string name = 1;
  string description = 2;
  int32 num_companies = 3;
  int32 num_assets  = 4;
}

message CompetitorPosition {
  string company = 1;
  repeated Asset assets = 2;
  string position = 3; // leader, challenger, follower, niche
}

message Asset {
  string name = 1;
  string phase = 2;
  string mechanism = 3;
}

message AnalyzeTechnologyLandscapeRequest {
  string technology = 1;
  string timeframe = 2;
}

message TechnologyLandscape {
  string technology = 1;
  repeated PatentCluster patent_clusters = 2;
  repeated KeyPlayer key_players = 3;
  repeated Trend trends = 4;
}

message PatentCluster {
  string cluster_id = 1;
  repeated string patents = 2;
  string assignee = 3;
  int32 patent_count = 4;
}

message KeyPlayer {
  string company = 1;
  int32 patent_count = 2;
  float market_share = 3;
}

message Trend {
  string trend = 1;
  string direction = 2; // emerging, declining, stable
  float growth_rate = 3;
}

message IdentifyThreatsRequest {
  string company_id = 1;
  string indication = 2;
}

message ThreatAnalysis {
  repeated Threat threats = 1;
  repeated Opportunity opportunities = 2;
}

message Threat {
  string type = 1;
  string description = 2;
  string source = 3;
  float severity = 4;
  google.protobuf.Timestamp detected_at = 5;
}

message Opportunity {
  string type = 1;
  string description = 2;
  float potential = 3;
}

message IdentifyLicensingOpportunitiesRequest {
  string focus_area = 1;
  string stage = 2;
}

message LicensingOpportunities {
  repeated LicensingOpportunity opportunities = 1;
}

message LicensingOpportunity {
  string asset = 1;
  string company = 2;
  string stage = 3;
  float attractiveness_score = 4;
  string rationale = 5;
}
```

---

## 9. Portfolio Management APIs

### 9.1 Portfolio Service (REST)

**GET /api/v1/portfolios**
Query params: `workspace_id`, `status`

Response:
```json
{
  "portfolios": [
    {
      "id": "port-uuid",
      "name": "Oncology Portfolio 2024",
      "workspace_id": "ws-uuid",
      "status": "active",
      "created_at": "2024-01-01T00:00:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "limit": 20
}
```

**POST /api/v1/portfolios**
```json
{
  "name": "Oncology Portfolio 2024",
  "workspace_id": "ws-uuid",
  "description": "Oncology assets for 2024"
}
```

**GET /api/v1/portfolios/{portfolio_id}/assets**

**POST /api/v1/portfolios/{portfolio_id}/assets**
```json
{
  "name": "HER2 Inhibitor X",
  "type": "small_molecule",
  "indication": "Breast Cancer",
  "phase": "Phase II"
}
```

**GET /api/v1/portfolios/{portfolio_id}/scores**

---

### 9.2 Scoring Engine Service (gRPC)

```protobuf
service ScoringEngineService {
  rpc ScoreAsset(ScoreAssetRequest) returns (AssetScore);
  rpc ScorePortfolio(ScorePortfolioRequest) returns (PortfolioScore);
  rpc CompareAssets(CompareAssetsRequest) returns (AssetComparison);
}

message ScoreAssetRequest {
  string asset_id = 1;
  repeated ScoringDimension dimensions = 2;
}

message ScoringDimension {
  string name = 1;
  float weight = 2;
  map<string, string> parameters = 3;
}

message AssetScore {
  string asset_id = 1;
  float composite_score = 2;
  repeated DimensionScore dimension_scores = 3;
  google.protobuf.Timestamp scored_at = 4;
}

message DimensionScore {
  string dimension = 1;
  float score = 2;
  float weight = 3;
  string explanation = 4;
  repeated Factor factors = 5;
}

message Factor {
  string name = 1;
  float value = 2;
  string contribution = 3; // positive, negative, neutral
}

message ScorePortfolioRequest {
  string portfolio_id = 1;
  repeated ScoringDimension dimensions = 2;
}

message PortfolioScore {
  string portfolio_id = 1;
  float composite_score = 2;
  repeated AssetScore asset_scores = 3;
  PortfolioMetrics metrics = 4;
}

message PortfolioMetrics {
  float risk_score = 1;
  float roi_potential = 2;
  float diversification = 3;
  float balance = 4;
}

message CompareAssetsRequest {
  repeated string asset_ids = 1;
  repeated ScoringDimension dimensions = 2;
}

message AssetComparison {
  repeated AssetScore scores = 1;
  repeated Comparison comparison = 2;
}

message Comparison {
  string dimension = 1;
  repeated AssetRanking ranking = 2;
}

message AssetRanking {
  string asset_id = 1;
  float score = 2;
  int32 rank = 3;
}
```

---

## 10. Collaboration APIs

### 10.1 Notebook Service (REST)

**GET /api/v1/notebooks**
Query params: `project_id`, `owner`, `tag`

Response:
```json
{
  "notebooks": [
    {
      "id": "nb-uuid",
      "title": "HER2 Target Validation",
      "project_id": "proj-uuid",
      "owner": "user-uuid",
      "created_at": "2024-01-01T00:00:00Z",
      "updated_at": "2024-01-01T00:00:00Z"
    }
  ],
  "total": 1,
  "page": 1,
  "limit": 20
}
```

**POST /api/v1/notebooks**
```json
{
  "title": "HER2 Target Validation",
  "project_id": "proj-uuid"
}
```

**GET /api/v1/notebooks/{notebook_id}**

**POST /api/v1/notebooks/{notebook_id}/cells**
```json
{
  "type": "markdown",
  "content": "# HER2 Target Analysis"
}
```

**PUT /api/v1/notebooks/{notebook_id}/cells/{cell_id}**

**DELETE /api/v1/notebooks/{notebook_id}/cells/{cell_id}**

**POST /api/v1/notebooks/{notebook_id}/versions**

**GET /api/v1/notebooks/{notebook_id}/versions/{version_id}**

**POST /api/v1/notebooks/{notebook_id}/export**
```json
{
  "format": "pdf"
}
```

---

### 10.2 Document Service (REST)

**GET /api/v1/documents**
Query params: `folder_id`, `type`, `search`

**POST /api/v1/documents**
```json
{
  "name": "Research Report.pdf",
  "folder_id": "folder-uuid",
  "type": "pdf"
}
```

**POST /api/v1/documents/{document_id}/upload**
Content-Type: multipart/form-data

**GET /api/v1/documents/{document_id}/download**

**GET /api/v1/documents/{document_id}/versions**

---

## 11. Data Integration APIs

### 11.1 Connector Service (REST)

**GET /api/v1/connectors**

**POST /api/v1/connectors**
```json
{
  "name": "PubMed Connector",
  "type": "literature",
  "config": {
    "api_key": "key",
    "rate_limit": 10
  }
}
```

**GET /api/v1/connectors/{connector_id}/health**

**POST /api/v1/connectors/{connector_id}/test**

---

## 12. Observability APIs

### 12.1 Health Check Service (REST)

**GET /api/v1/health**
Response:
```json
{
  "status": "healthy",
  "timestamp": "2024-01-01T00:00:00Z",
  "services": [
    {
      "name": "auth-service",
      "status": "healthy",
      "latency_ms": 5
    },
    {
      "name": "graph-service",
      "status": "healthy",
      "latency_ms": 10
    }
  ]
}
```

**GET /api/v1/health/{service_name}**

---

### 12.2 Metrics Service (REST)

**GET /api/v1/metrics**
Query params: `service`, `metric`, `from`, `to`

Response:
```json
{
  "metrics": [
    {
      "name": "request_count",
      "value": 1000,
      "timestamp": "2024-01-01T00:00:00Z",
      "labels": {
        "service": "auth-service",
        "endpoint": "/login"
      }
    }
  ]
}
```

---

## WebSocket APIs

### Real-time Collaboration

**WS /api/v1/ws/collaboration/{notebook_id}**

Message format:
```json
{
  "type": "cell_update",
  "cell_id": "cell-uuid",
  "content": "new content",
  "user_id": "user-uuid"
}
```

### Agent Streaming

**WS /api/v1/ws/agent/{conversation_id}**

Message format:
```json
{
  "type": "agent_response",
  "content": "partial response",
  "status": "in_progress"
}
```

---

## API Standards

### Error Responses

All APIs return consistent error responses:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid input parameter",
    "details": {
      "field": "email",
      "issue": "Invalid email format"
    },
    "request_id": "req-uuid",
    "timestamp": "2024-01-01T00:00:00Z"
  }
}
```

### Error Codes

- `VALIDATION_ERROR`: Invalid input
- `AUTHENTICATION_ERROR`: Failed authentication
- `AUTHORIZATION_ERROR`: Insufficient permissions
- `NOT_FOUND`: Resource not found
- `CONFLICT`: Resource conflict
- `RATE_LIMIT_EXCEEDED`: Too many requests
- `INTERNAL_ERROR`: Server error
- `SERVICE_UNAVAILABLE`: Service down

### Pagination

List endpoints support pagination:

Query params:
- `page`: Page number (default: 1)
- `limit`: Items per page (default: 20, max: 100)

Response:
```json
{
  "items": [...],
  "total": 100,
  "page": 1,
  "limit": 20,
  "pages": 5
}
```

### Filtering

Query params:
- `filter[field]`: Field filter
- `sort`: Sort field
- `order`: Sort order (asc, desc)

Example:
```
GET /api/v1/trials?filter[status]=Recruiting&sort=start_date&order=desc
```

---

## SDKs

### Python SDK

```python
from ai_rxos import Client

client = Client(api_key="your-api-key")

# Knowledge graph
gene = client.graph.get_node("gene:BRCA1")
relationships = client.graph.get_relationships(from_id="gene:BRCA1")

# AI agents
response = client.agents.invoke(
    agent_id="literature-agent",
    input="Find recent HER2 publications"
)

# Search
results = client.search.search("HER2 breast cancer", limit=10)

# Molecules
molecule = client.molecules.get("mol-uuid")
docking = client.docking.dock(target_id="target-123", smiles="...")
```

### TypeScript SDK

```typescript
import { Client } from '@ai-rxos/sdk';

const client = new Client({ apiKey: 'your-api-key' });

// Knowledge graph
const gene = await client.graph.getNode('gene:BRCA1');
const relationships = await client.graph.getRelationships({ from: 'gene:BRCA1' });

// AI agents
const response = await client.agents.invoke({
  agentId: 'literature-agent',
  input: 'Find recent HER2 publications'
});

// Search
const results = await client.search.search('HER2 breast cancer', { limit: 10 });

// Molecules
const molecule = await client.molecules.get('mol-uuid');
const docking = await client.docking.dock({
  targetId: 'target-123',
  smiles: '...'
});
```
