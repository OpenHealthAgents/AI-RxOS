import express from "express";
import { toNodeHandler } from "better-auth/node";

import { auth } from "./auth.js";
import { config } from "./config.js";

const app = express();

// BetterAuth's own router (registration/session/its JWT-plugin endpoints)
// is mounted at /api/auth/*, namespaced away from the legacy
// /api/v1/auth/* prefix served by services/auth (proxied by
// apps/api-gateway) so the two can run side by side without a routing
// conflict. Must be mounted before express.json() — BetterAuth parses
// the request body itself.
app.all("/api/auth/*", toNodeHandler(auth));

app.use(express.json());

app.get("/healthz", (_req, res) => {
  res.json({ status: "ok", service: "auth-adapter" });
});

app.listen(Number(config.port), () => {
  // eslint-disable-next-line no-console
  console.log(JSON.stringify({ level: "INFO", msg: "auth-adapter service listening", port: config.port }));
});
