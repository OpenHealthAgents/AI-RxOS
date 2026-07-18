# infra

- `k8s/` — raw cluster-bootstrap manifests (namespaces, baseline network
  policies). Apply once per cluster, before any Helm release:
  `kubectl apply -f infra/k8s/`
- `helm/ai-rxos/` — the umbrella Helm chart that deploys all 13 application
  services plus (optionally, per environment) in-cluster PostgreSQL+pgvector,
  Neo4j, Redis, and OpenSearch.
- `postgres/init.sql` — first-boot init script for the docker-compose
  Postgres container (enables `pgvector`/`uuid-ossp`); Helm's PostgreSQL
  dependency handles this via its own image (`pgvector/pgvector:pg16`).

## Deploying with Helm

```bash
helm dependency update infra/helm/ai-rxos

# local/dev cluster (kind, minikube, k3d) — in-cluster dependencies, no ingress
helm install ai-rxos infra/helm/ai-rxos \
  -f infra/helm/ai-rxos/values.yaml \
  -f infra/helm/ai-rxos/values-dev.yaml \
  --create-namespace -n ai-rxos-development

# production — managed AWS services, external secrets, ingress+TLS
helm install ai-rxos infra/helm/ai-rxos \
  -f infra/helm/ai-rxos/values.yaml \
  -f infra/helm/ai-rxos/values-prod.yaml \
  -n ai-rxos-production
```

Update in place with `helm upgrade` using the same `-f` flags.
