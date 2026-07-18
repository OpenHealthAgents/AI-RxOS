package gateway

import (
	"log/slog"
	"net/http"
	"net/http/httputil"
	"net/url"
)

// newReverseProxy builds a reverse proxy to target that rewrites errors into
// JSON and logs upstream failures instead of leaking Go's default HTML page.
func newReverseProxy(name, target string) http.Handler {
	u, err := url.Parse(target)
	if err != nil {
		slog.Error("invalid upstream url", "service", name, "target", target, "err", err)
	}

	proxy := httputil.NewSingleHostReverseProxy(u)
	origDirector := proxy.Director
	proxy.Director = func(r *http.Request) {
		origDirector(r)
		r.Header.Set("X-Forwarded-Gateway", "ai-rxos-api-gateway")
	}
	proxy.ErrorHandler = func(w http.ResponseWriter, r *http.Request, err error) {
		slog.Error("upstream error", "service", name, "path", r.URL.Path, "err", err)
		writeJSONError(w, http.StatusBadGateway, "upstream_unavailable", "the "+name+" service is unavailable")
	}
	return proxy
}
