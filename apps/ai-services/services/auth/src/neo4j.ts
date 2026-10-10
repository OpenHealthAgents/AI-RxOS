import { config } from "./config.js";

export interface Neo4jCheckResult {
  available: boolean;
  allowed: boolean;
  reason?: string;
}

let driver: any = null;
let neo4jModule: any = null;

async function getDriver() {
  if (driver) return driver;
  if (!config.neo4jUrl) return null;

  try {
    neo4jModule = await import("neo4j-driver");
    const auth = config.neo4jUser
      ? neo4jModule.auth.basic(config.neo4jUser, config.neo4jPassword)
      : neo4jModule.auth.none();

    driver = neo4jModule.driver(config.neo4jUrl, auth, {
      encrypted: config.neo4jEncrypted ? "ENCRYPTION_ON" : "ENCRYPTION_OFF",
      maxConnectionPoolSize: config.neo4jPoolSize,
      maxTransactionRetryTime: config.neo4jMaxRetryTimeMs,
    });
    return driver;
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error("Neo4j client import failed:", e);
    return null;
  }
}

function createSession(accessMode: "READ" | "WRITE" = "READ") {
  if (!driver || !neo4jModule) throw new Error("neo4j_not_initialized");
  return driver.session({
    database: config.neo4jDatabase,
    defaultAccessMode: accessMode === "WRITE" ? neo4jModule.session.WRITE : neo4jModule.session.READ,
  });
}

export async function initNeo4jSchema() {
  const d = await getDriver();
  if (!d) return { ok: false, message: "neo4j_unavailable" };

  let session: any = null;
  try {
    session = createSession("WRITE");
    await session.executeWrite(async (tx: any) => {
      await tx.run(`CREATE CONSTRAINT IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE`);
      await tx.run(`CREATE CONSTRAINT IF NOT EXISTS FOR (r:Resource) REQUIRE r.id IS UNIQUE`);
      await tx.run(`CREATE CONSTRAINT IF NOT EXISTS FOR (t:Tenant) REQUIRE t.id IS UNIQUE`);
      await tx.run(`CREATE INDEX IF NOT EXISTS FOR (u:User) ON (u.tenantId)`);
      await tx.run(`CREATE INDEX IF NOT EXISTS FOR (r:Resource) ON (r.tenantId)`);
      await tx.run(`CREATE INDEX IF NOT EXISTS FOR (t:Tenant) ON (t.id)`);
    });
    return { ok: true };
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error("Neo4j schema init failed:", e);
    return { ok: false, message: "schema_init_failed" };
  } finally {
    try {
      await session?.close();
    } catch (_) {}
  }
}

function buildTenantClause(tenantId?: string) {
  if (!tenantId) return "";
  return "WHERE u.tenantId = $tenantId AND r.tenantId = $tenantId";
}

export async function isAllowedByNeo4j(subjectId: string, resourceId: string, action: string, tenantId?: string): Promise<Neo4jCheckResult> {
  const d = await getDriver();
  if (!d) return { available: false, allowed: true };

  let session: any = null;
  try {
    session = createSession("READ");
    const result = await session.run(
      `MATCH (u:User {id:$subjectId})
       MATCH (r:Resource {id:$resourceId})
       ${buildTenantClause(tenantId)}
       OPTIONAL MATCH (u)-[rel:HAS_ACCESS {action:$action}]->(r)
       RETURN count(rel) AS c`,
      { subjectId, resourceId, action, tenantId }
    );
    const count = result.records?.[0]?.get?.("c")?.toNumber?.() ?? Number(result.records?.[0]?.get?.("c")) ?? 0;
    if (count > 0) {
      return { available: true, allowed: true };
    }
    return { available: true, allowed: false, reason: "Graph-based policy denied access" };
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error("Neo4j authorization check failed:", e);
    return { available: false, allowed: true };
  } finally {
    try {
      await session?.close();
    } catch (_) {}
  }
}

export async function seedPermission(subjectId: string, resourceId: string, action: string, tenantId?: string) {
  const d = await getDriver();
  if (!d) return { ok: false, message: "neo4j_unavailable" };

  let session: any = null;
  try {
    session = createSession("WRITE");
    if (tenantId) {
      await session.run(
        `MERGE (t:Tenant {id:$tenantId})
         MERGE (u:User {id:$subjectId})
         ON CREATE SET u.tenantId = $tenantId
         MERGE (r:Resource {id:$resourceId})
         ON CREATE SET r.tenantId = $tenantId
         MERGE (u)-[:MEMBER_OF]->(t)
         MERGE (r)-[:BELONGS_TO]->(t)
         MERGE (u)-[rel:HAS_ACCESS {action:$action}]->(r)
         RETURN rel`,
        { subjectId, resourceId, action, tenantId }
      );
    } else {
      await session.run(
        `MERGE (u:User {id:$subjectId})
         MERGE (r:Resource {id:$resourceId})
         MERGE (u)-[rel:HAS_ACCESS {action:$action}]->(r)
         RETURN rel`,
        { subjectId, resourceId, action }
      );
    }
    return { ok: true };
  } catch (e) {
    // eslint-disable-next-line no-console
    console.error("Neo4j seed failed:", e);
    return { ok: false, message: "seed_failed" };
  } finally {
    try {
      await session?.close();
    } catch (_) {}
  }
}
