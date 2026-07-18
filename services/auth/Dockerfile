FROM golang:1.22-alpine AS build
WORKDIR /src
RUN apk add --no-cache git
COPY services/auth/ .
RUN go mod tidy
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /out/auth ./cmd/auth

FROM gcr.io/distroless/static-debian12:nonroot AS runtime
COPY --from=build /out/auth /auth
USER nonroot:nonroot
EXPOSE 8081
ENTRYPOINT ["/auth"]
