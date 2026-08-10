import { drizzle } from "drizzle-orm/postgres-js";
import postgres from "postgres";
import * as schema from "./schema";

const connectionString = process.env.DATABASE_URL;
if (!connectionString) {
  throw new Error("DATABASE_URL environment variable is not set");
}

// Prevent multiple connections in Next.js dev hot-reload
const globalForDb = globalThis as unknown as { _pg: postgres.Sql | undefined };
const pg = globalForDb._pg ?? postgres(connectionString, { max: 5 });
if (process.env.NODE_ENV !== "production") globalForDb._pg = pg;

export const db = drizzle(pg, { schema });
