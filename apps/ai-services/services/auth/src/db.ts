import pg from "pg";
import { readFileSync, readdirSync } from "fs";
import { config } from "./config.js";

const { Pool } = pg;
const migrationsDir = new URL("../migrations/", import.meta.url);
const migrationFiles = readdirSync(migrationsDir)
  .filter((file) => file.endsWith(".sql"))
  .sort();
const schema = migrationFiles
  .map((file) => readFileSync(new URL(`../migrations/${file}`, import.meta.url), "utf8"))
  .join("\n\n");

let databaseInitializationPromise: Promise<void> | null = null;

export async function initDatabase() {
  if (databaseInitializationPromise) {
    await databaseInitializationPromise;
    return;
  }

  databaseInitializationPromise = (async () => {
    const pool = new Pool({ connectionString: config.databaseUrl });
    try {
      console.log("Initializing Postgres database schema...");
      await pool.query("SELECT pg_advisory_lock(hashtext('ai_rxos_auth_schema_init'))");
      await pool.query(schema);
      console.log("Database schema initialized successfully (RLS and Immutable Audit Log triggers configured).");
    } catch (err) {
      console.error("Database initialization failed:", err);
      throw err;
    } finally {
      try {
        await pool.query("SELECT pg_advisory_unlock(hashtext('ai_rxos_auth_schema_init'))");
      } catch {
        // Ignore unlock failures; the session will release the lock on disconnect.
      }
      await pool.end();
    }
  })();

  try {
    await databaseInitializationPromise;
  } catch (err) {
    databaseInitializationPromise = null;
    throw err;
  }
}
