# api-gateway

Go reverse-proxy gateway: JWT validation, per-IP rate limiting, CORS, request
logging, and prefix-based routing to every backend service. Config is
entirely env-driven (see `internal/config/config.go`), so the same binary
runs unmodified in docker-compose and Kubernetes.

## Local dev

```bash
go mod tidy   # generates go.sum on first run
go run ./cmd/gateway
```

## Adding a route

Add a `prefix -> upstream URL` entry to the `routes` map in
`internal/gateway/router.go`, and (if it should require auth) leave it off
`publicPaths`.
