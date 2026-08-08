import { drizzle } from "drizzle-orm/postgres-js";
import postgres from "postgres";
import * as schema from "./schema";

const connectionString = process.env.DATABASE_URL;
if (!connectionString) {
  throw new Error("DATABASE_URL environment variable is not set");
}

// Prevent multiple connections in Next.js dev hot-reload
const globalForDb = globalThis as unknown as { _db: any };
export const db = globalForDb._db ?? drizzle(connectionString);
if (process.env.NODE_ENV !== "production") globalForDb._db = db;
