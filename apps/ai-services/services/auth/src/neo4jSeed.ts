import { config } from "./config.js";

async function run() {
  const args = process.argv.slice(2);
  const initSchema = args.includes("--init-schema");
  const seed = args.includes("--seed");

  if (!initSchema && !seed) {
    console.error("Usage: tsx src/neo4jSeed.ts -- --init-schema|--seed");
    process.exit(1);
  }

  try {
    const neo4j = await import("neo4j-driver");
    const auth = config.neo4jUser
      ? neo4j.auth.basic(config.neo4jUser, config.neo4jPassword)
      : neo4j.auth.none();
    const driver = neo4j.driver(config.neo4jUrl, auth, {
      encrypted: config.neo4jEncrypted ? "ENCRYPTION_ON" : "ENCRYPTION_OFF",
      maxConnectionPoolSize: config.neo4jPoolSize,
      maxTransactionRetryTime: config.neo4jMaxRetryTimeMs,
    });

    const session = driver.session({
      database: config.neo4jDatabase,
      defaultAccessMode: neo4j.session.WRITE,
    });

    if (initSchema) {
      console.log("Initializing Neo4j schema...");
      await session.executeWrite(async (tx: any) => {
        await tx.run(`CREATE CONSTRAINT IF NOT EXISTS FOR (u:User) REQUIRE u.id IS UNIQUE`);
        await tx.run(`CREATE CONSTRAINT IF NOT EXISTS FOR (r:Resource) REQUIRE r.id IS UNIQUE`);
        await tx.run(`CREATE CONSTRAINT IF NOT EXISTS FOR (t:Tenant) REQUIRE t.id IS UNIQUE`);
        await tx.run(`CREATE INDEX IF NOT EXISTS FOR (u:User) ON (u.tenantId)`);
        await tx.run(`CREATE INDEX IF NOT EXISTS FOR (r:Resource) ON (r.tenantId)`);
        await tx.run(`CREATE INDEX IF NOT EXISTS FOR (t:Tenant) ON (t.id)`);
      });
      console.log("Neo4j schema initialized.");
    }

    if (seed) {
      console.log("Seeding example Neo4j permissions...");
      await session.executeWrite(async (tx: any) => {
        await tx.run(`MERGE (t:Tenant {id:$tenantId})`, { tenantId: "tenant-example" });
        await tx.run(`MERGE (u:User {id:$subjectId}) ON CREATE SET u.tenantId = $tenantId`, {
          subjectId: "user-example",
          tenantId: "tenant-example",
        });
        await tx.run(`MERGE (r:Resource {id:$resourceId}) ON CREATE SET r.tenantId = $tenantId`, {
          resourceId: "resource-example",
          tenantId: "tenant-example",
        });
        await tx.run(`MERGE (u:User {id:$subjectId})-[rel:HAS_ACCESS {action:$action}]->(r)`, {
          subjectId: "user-example",
          resourceId: "resource-example",
          action: "read",
        });
      });
      console.log("Neo4j seed complete.");
    }

    await session.close();
    await driver.close();
    process.exit(0);
  } catch (e) {
    console.error("Neo4j seed utility failed:", e);
    process.exit(1);
  }
}

run();
