# Deployment Architecture - AI-RxOS

## Overview
AI-RxOS is deployed on Kubernetes with multi-region support for high availability and disaster recovery. The architecture uses cloud-native technologies for scalability, observability, and security.

---

## Infrastructure Overview

### Cloud Providers
- **Primary**: AWS (us-east-1)
- **Secondary**: AWS (us-west-2) for disaster recovery
- **Optional**: Azure AKS or GCP GKE for enterprise deployments

### Kubernetes Clusters
- **Development**: Single cluster (us-east-1)
- **Staging**: HA cluster (us-east-1)
- **Production**: Multi-region clusters (us-east-1, us-west-2)

---

## Cluster Architecture

### Production Cluster (us-east-1)

```
┌─────────────────────────────────────────────────────────────┐
│                    VPC (10.0.0.0/16)                        │
├─────────────────────────────────────────────────────────────┤
│  Public Subnets (10.0.1.0/24, 10.0.2.0/24)                  │
│  - Load Balancers                                           │
│  - NAT Gateways                                             │
├─────────────────────────────────────────────────────────────┤
│  Private Subnets (10.0.10.0/24, 10.0.11.0/24)               │
│  - Kubernetes Control Plane                                 │
│  - Application Services                                     │
├─────────────────────────────────────────────────────────────┤
│  Private Subnets (10.0.20.0/24, 10.0.21.0/24)               │
│  - Databases                                                │
│  - Redis                                                    │
│  - Kafka                                                    │
├─────────────────────────────────────────────────────────────┤
│  Private Subnets (10.0.30.0/24, 10.0.31.0/24)               │
│  - GPU Nodes                                                │
│  - Inference Services                                       │
└─────────────────────────────────────────────────────────────┘
```

### DR Cluster (us-west-2)

```
┌─────────────────────────────────────────────────────────────┐
│                    VPC (10.1.0.0/16)                        │
├─────────────────────────────────────────────────────────────┤
│  Similar subnet structure to production                     │
│  - Smaller scale (1/3 of production)                        │
│  - Hot standby for critical services                        │
└─────────────────────────────────────────────────────────────┘
```

---

## Kubernetes Namespaces

### Namespace Strategy
- **default**: Core platform services
- **ai-rxos-production**: Application services
- **ai-rxos-staging**: Staging environment
- **ai-rxos-development**: Development environment
- **monitoring**: Observability stack
- **infrastructure**: Infrastructure services
- **gpu-workloads**: GPU-intensive workloads

### Namespace Isolation
- Network policies between namespaces
- Resource quotas per namespace
- RBAC per namespace
- Separate service accounts

---

## Service Deployment

### 1. API Gateway
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-gateway
  namespace: default
spec:
  replicas: 3
  selector:
    matchLabels:
      app: api-gateway
  template:
    metadata:
      labels:
        app: api-gateway
    spec:
      containers:
      - name: kong
        image: kong:3.4
        ports:
        - containerPort: 8000
        resources:
          requests:
            cpu: 500m
            memory: 512Mi
          limits:
            cpu: 2000m
            memory: 2Gi
---
apiVersion: v1
kind: Service
metadata:
  name: api-gateway
  namespace: default
spec:
  type: LoadBalancer
  ports:
  - port: 443
    targetPort: 8443
  selector:
    app: api-gateway
```

### 2. Identity Service
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: identity-service
  namespace: ai-rxos-production
spec:
  replicas: 3
  selector:
    matchLabels:
      app: identity-service
  template:
    metadata:
      labels:
        app: identity-service
    spec:
      containers:
      - name: identity-service
        image: ai-rxos/identity-service:v1.0.0
        ports:
        - containerPort: 8080
        env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: database-secrets
              key: url
        resources:
          requests:
            cpu: 250m
            memory: 256Mi
          limits:
            cpu: 1000m
            memory: 1Gi
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: identity-service-hpa
  namespace: ai-rxos-production
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: identity-service
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
```

### 3. Graph Service (Neo4j)
```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: neo4j
  namespace: ai-rxos-production
spec:
  serviceName: neo4j
  replicas: 3
  selector:
    matchLabels:
      app: neo4j
  template:
    metadata:
      labels:
        app: neo4j
    spec:
      containers:
      - name: neo4j
        image: neo4j:5.12
        ports:
        - containerPort: 7474
        - containerPort: 7687
        env:
        - name: NEO4J_AUTH
          value: "neo4j/password"
        resources:
          requests:
            cpu: 1000m
            memory: 4Gi
          limits:
            cpu: 4000m
            memory: 16Gi
        volumeMounts:
        - name: data
          mountPath: /data
  volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      accessModes: [ "ReadWriteOnce" ]
      storageClassName: gp3-encrypted
      resources:
        requests:
          storage: 500Gi
```

### 4. Inference Service (GPU)
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: inference-service
  namespace: gpu-workloads
spec:
  replicas: 2
  selector:
    matchLabels:
      app: inference-service
  template:
    metadata:
      labels:
        app: inference-service
    spec:
      nodeSelector:
        gpu: "true"
      containers:
      - name: inference-service
        image: ai-rxos/inference-service:v1.0.0
        ports:
        - containerPort: 8080
        resources:
          requests:
            cpu: 2000m
            memory: 8Gi
            nvidia.com/gpu: 1
          limits:
            cpu: 8000m
            memory: 32Gi
            nvidia.com/gpu: 1
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: inference-service-hpa
  namespace: gpu-workloads
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: inference-service
  minReplicas: 2
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: nvidia.com/gpu
      target:
        type: Utilization
        averageUtilization: 80
```

### 5. Kafka Cluster
```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: kafka
  namespace: infrastructure
spec:
  serviceName: kafka
  replicas: 3
  selector:
    matchLabels:
      app: kafka
  template:
    metadata:
      labels:
        app: kafka
    spec:
      containers:
      - name: kafka
        image: confluentinc/cp-kafka:7.5
        ports:
        - containerPort: 9092
        env:
        - name: KAFKA_ZOOKEEPER_CONNECT
          value: "zookeeper:2181"
        - name: KAFKA_ADVERTISED_LISTENERS
          value: "PLAINTEXT://kafka:9092"
        - name: KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR
          value: "3"
        resources:
          requests:
            cpu: 500m
            memory: 2Gi
          limits:
            cpu: 2000m
            memory: 8Gi
        volumeMounts:
        - name: data
          mountPath: /var/lib/kafka/data
  volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      accessModes: [ "ReadWriteOnce" ]
      storageClassName: gp3-encrypted
      resources:
        requests:
          storage: 200Gi
```

---

## Database Deployment

### PostgreSQL (RDS)
- **Engine**: PostgreSQL 15
- **Instance**: db.r6g.4xlarge (16 vCPU, 128 GiB RAM)
- **Storage**: 2 TB gp3, 5000 IOPS, 125 MB/s
- **Multi-AZ**: Yes
- **Replication**: 1 read replica
- **Backup**: 7-day retention, point-in-time recovery
- **Encryption**: At rest and in transit

### Neo4j (Kubernetes)
- **Version**: 5.12
- **Deployment**: 3-node cluster
- **Storage**: 500 GiB per node
- **Memory**: 16 GiB per node
- **CPU**: 4 vCPU per node
- **Backup**: Daily snapshots to S3

### Redis (ElastiCache)
- **Engine**: Redis 7
- **Mode**: Cluster mode enabled
- **Node Type**: cache.r6g.large
- **Shards**: 3
- **Replicas per shard**: 1
- **Multi-AZ**: Yes
- **Encryption**: At rest and in transit

### OpenSearch (AWS OpenSearch)
- **Version**: 2.11
- **Domain**: ai-rxos-search
- **Instance Type**: r6g.2xlarge.search
- **Instance Count**: 6 (3 data nodes, 3 master nodes)
- **Storage**: 1 TB per data node
- **Multi-AZ**: Yes
- **Encryption**: At rest and in transit

### Object Storage (S3)
- **Buckets**: ai-rxos-documents, ai-rxos-molecules, ai-rxos-models
- **Storage Class**: Intelligent-Tiering
- **Versioning**: Enabled
- **Encryption**: SSE-S3
- **Lifecycle**: Transition to Glacier after 90 days

---

## GPU Infrastructure

### GPU Node Groups
- **Instance Type**: p4d.24xlarge (8x A100 40GB)
- **Count**: 4 nodes (32 GPUs total)
- **Autoscaling**: 2-8 nodes
- **Placement**: GPU subnet

### GPU Workload Scheduling
```yaml
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: gpu-high-priority
value: 1000
globalDefault: false
description: "High priority GPU workloads"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: docking-service
  namespace: gpu-workloads
spec:
  replicas: 2
  selector:
    matchLabels:
      app: docking-service
  template:
    metadata:
      labels:
        app: docking-service
    spec:
      priorityClassName: gpu-high-priority
      nodeSelector:
        gpu: "true"
      containers:
      - name: docking-service
        image: ai-rxos/docking-service:v1.0.0
        resources:
          limits:
            nvidia.com/gpu: 2
```

---

## Networking

### Ingress
- **Ingress Controller**: NGINX
- **SSL/TLS**: AWS Certificate Manager
- **TLS Termination**: At load balancer
- **HTTP/2**: Enabled
- **WebSocket**: Enabled

### Service Mesh
- **Mesh**: Istio
- **mTLS**: Enabled between services
- **Traffic Management**: Virtual services, destination rules
- **Observability**: Distributed tracing, metrics

### Network Policies
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: deny-all
  namespace: ai-rxos-production
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  - Egress
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-dns
  namespace: ai-rxos-production
spec:
  podSelector: {}
  policyTypes:
  - Egress
  egress:
  - to:
    - namespaceSelector:
        matchLabels:
          name: kube-system
    ports:
    - protocol: UDP
      port: 53
```

---

## Security

### Secrets Management
- **Secret Store**: AWS Secrets Manager
- **Rotation**: Automatic rotation for database credentials
- **Encryption**: KMS-encrypted secrets
- **Access**: IAM-based access

### IAM Roles
- **Pod Identity**: IRSA (IAM Roles for Service Accounts)
- **Least Privilege**: Service-specific IAM roles
- **Audit**: CloudTrail logging

### Security Groups
- **Ingress**: Only from load balancer
- **Egress**: Only to required services
- **Monitoring**: VPC Flow Logs

### Compliance
- **SOC 2**: Compliant controls
- **HIPAA**: Available for healthcare customers
- **ISO 27001**: Security controls
- **GDPR**: Data protection measures

---

## Observability

### Monitoring Stack
- **Metrics**: Prometheus + Grafana
- **Logging**: ELK Stack (Elasticsearch, Logstash, Kibana)
- **Tracing**: Jaeger
- **Alerting**: Alertmanager + PagerDuty

### Prometheus Configuration
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: prometheus-config
  namespace: monitoring
data:
  prometheus.yml: |
    global:
      scrape_interval: 15s
    scrape_configs:
    - job_name: 'kubernetes-pods'
      kubernetes_sd_configs:
      - role: pod
      relabel_configs:
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
        action: keep
        regex: true
```

### Grafana Dashboards
- Service health
- Request latency
- Error rates
- GPU utilization
- Database performance
- Kafka lag
- Agent metrics

### Logging
- **Log Aggregation**: Fluentd → Elasticsearch
- **Log Retention**: 30 days
- **Log Parsing**: Structured JSON logs
- **Log Search**: Kibana

### Tracing
- **Tracing Backend**: Jaeger
- **Sampling**: 1% for production, 10% for staging
- **Propagation**: W3C trace context
- **Retention**: 7 days

---

## Disaster Recovery

### RPO/RTO
- **RPO**: 15 minutes
- **RTO**: 60 minutes
- **Backup Frequency**: Every 15 minutes for PostgreSQL, daily for Neo4j

### Backup Strategy
- **PostgreSQL**: WAL archiving to S3, daily snapshots
- **Neo4j**: Daily snapshots to S3
- **S3**: Cross-region replication
- **EBS**: Daily snapshots

### Failover Process
1. DNS failover to DR region
2. Scale up DR cluster
3. Restore from latest backup
4. Verify data integrity
5. Switch traffic
6. Scale down primary region

### Testing
- Monthly DR drills
- Automated failover tests
- Backup restoration tests

---

## CI/CD Pipeline

### Pipeline Stages
1. **Build**: Docker image build
2. **Test**: Unit tests, integration tests
3. **Security Scan**: Trivy, Snyk
4. **Deploy to Dev**: Development cluster
5. **E2E Tests**: End-to-end tests
6. **Deploy to Staging**: Staging cluster
7. **Load Tests**: Performance testing
8. **Deploy to Production**: Production cluster

### Deployment Strategy
- **Blue-Green**: Zero-downtime deployments
- **Canary**: Gradual rollout (10% → 50% → 100%)
- **Rollback**: Automatic on failure

### GitOps
- **Tool**: ArgoCD
- **Repository**: Git repo for manifests
- **Sync**: Automatic sync to cluster
- **Drift Detection**: Alert on configuration drift

---

## Infrastructure as Code

### Terraform
- **Provider**: AWS
- **State**: S3 backend with DynamoDB locking
- **Modules**: Reusable infrastructure modules
- **Environments**: Separate workspaces for dev/staging/prod

### Example Terraform Module
```hcl
module "eks_cluster" {
  source = "./modules/eks"
  
  cluster_name    = "ai-rxos-production"
  cluster_version = "1.28"
  
  vpc_id          = module.vpc.vpc_id
  subnet_ids      = module.vpc.private_subnet_ids
  
  node_groups = {
    general = {
      instance_type = "m6g.xlarge"
      min_size      = 3
      max_size      = 10
      desired_size  = 3
    }
    
    gpu = {
      instance_type = "p4d.24xlarge"
      min_size      = 2
      max_size      = 8
      desired_size  = 2
      gpu           = true
    }
  }
}
```

### Helm Charts
- **Charts**: Custom Helm charts for services
- **Repository**: Helm repository in S3
- **Values**: Environment-specific values files
- **Dependencies**: Chart dependencies managed

---

## Scaling

### Horizontal Pod Autoscaler (HPA)
- **CPU**: Scale at 70% utilization
- **Memory**: Scale at 80% utilization
- **Custom Metrics**: Request rate, queue length
- **Scale Down**: Stabilization window of 5 minutes

### Vertical Pod Autoscaler (VPA)
- **Mode**: Off for production, Recommender for analysis
- **Update Policy**: Manual updates
- **Resource Limits**: Based on recommendations

### Cluster Autoscaler
- **Scale Up**: When pods are pending
- **Scale Down**: When nodes are underutilized
- **Scale Down Period**: 10 minutes
- **Node Groups**: Separate scaling per node group

---

## Cost Optimization

### Reserved Instances
- **Compute**: 1-year or 3-year reserved instances for baseline
- **Savings Plans**: Compute savings plans for flexible usage

### Spot Instances
- **Development**: Spot instances for dev/test
- **Batch Jobs**: Spot instances for batch processing
- **Fallback**: On-demand fallback

### Storage Optimization
- **S3 Lifecycle**: Transition to cheaper tiers
- **EBS**: gp3 for most workloads, io2 for high IOPS
- **Compression**: Enable compression where applicable

### Monitoring
- **Cost Alerts**: AWS Budgets
- **Cost Allocation**: Tags for cost allocation
- **Regular Review**: Monthly cost review

---

## Multi-Region Deployment

### Active-Active Strategy
- **Primary Region**: us-east-1 (handles 70% traffic)
- **Secondary Region**: us-west-2 (handles 30% traffic)
- **DNS**: Route53 with latency-based routing
- **Data Replication**: Cross-region replication

### Data Replication
- **PostgreSQL**: Logical replication to DR region
- **Neo4j**: Causal clustering across regions
- **S3**: Cross-region replication
- **Kafka**: MirrorMaker for topic replication

### Failover
- **Automatic**: Health check-based failover
- **Manual**: Manual failover for planned maintenance
- **DNS**: Route53 health checks
- **RTO**: 5 minutes for automatic failover

---

## Performance

### Service Level Objectives (SLOs)
- **API Latency**: P95 < 500ms
- **Search Latency**: P95 < 2s
- **AI Response**: P95 < 10s
- **Availability**: 99.9% (43.2 minutes/month downtime)
- **Error Rate**: < 0.1%

### Performance Optimization
- **Caching**: Redis for frequently accessed data
- **CDN**: CloudFront for static assets
- **Connection Pooling**: Database connection pooling
- **Query Optimization**: Indexed queries, query caching

---

## Maintenance

### Update Strategy
- **Kubernetes**: Monthly minor version updates
- **Services**: Rolling updates with zero downtime
- **Databases**: Maintenance windows for major updates
- **OS**: Monthly security patches

### Patch Management
- **Security Patches**: Automated patching
- **CVE Scanning**: Regular vulnerability scanning
- **Patch Testing**: Test in staging before production

---

## Documentation

### Runbooks
- **Incident Response**: Step-by-step incident response
- **Deployment Runbook**: Deployment procedures
- **DR Runbook**: Disaster recovery procedures
- **Maintenance Runbook**: Maintenance procedures

### Architecture Diagrams
- **C4 Model**: System context, containers, components
- **Network Diagram**: Network topology
- **Data Flow**: Data flow diagrams
- **Deployment Diagram**: Deployment architecture

---

## Compliance and Auditing

### Audit Logging
- **API Calls**: CloudTrail for AWS API calls
- **Service Logs**: Application audit logs
- **Access Logs**: Load balancer access logs
- **Retention**: 7 years for compliance

### Compliance Reports
- **SOC 2**: Annual SOC 2 Type II report
- **HIPAA**: BAA for healthcare customers
- **ISO 27001**: Annual certification
- **Penetration Testing**: Quarterly penetration tests

---

## Support

### Support Tiers
- **Tier 1**: Automated monitoring and alerting
- **Tier 2**: On-call engineering team
- **Tier 3**: Subject matter experts
- **Tier 4**: Vendor support

### On-Call Rotation
- **Schedule**: Weekly rotation
- **Coverage**: 24/7 coverage
- **Escalation**: Defined escalation paths
- **Runbooks**: Comprehensive runbooks

### Incident Management
- **Severity Levels**: P1 (critical) to P4 (low)
- **Response Times**: Defined by severity
- **Communication**: Status page updates
- **Post-Mortem**: Post-incident reviews
