import {
  pgTable,
  uuid,
  text,
  boolean,
  jsonb,
  timestamp,
} from "drizzle-orm/pg-core";
import type { Citation } from "@/lib/validations/triage";

interface RestrictionHit {
  code: string;
  reason: string;
  layer: string;
  ts: string;
}

export const triageSessions = pgTable("triage_sessions", {
  id: uuid("id").primaryKey().defaultRandom(),
  sessionToken: text("session_token").unique().notNull(),
  createdAt: timestamp("created_at").defaultNow().notNull(),
  escalated: boolean("escalated").default(false).notNull(),
  restrictionHits: jsonb("restriction_hits")
    .$type<RestrictionHit[]>()
    .default([]),
});

export const triageMessages = pgTable("triage_messages", {
  id: uuid("id").primaryKey().defaultRandom(),
  sessionId: uuid("session_id")
    .notNull()
    .references(() => triageSessions.id, { onDelete: "cascade" }),
  role: text("role", { enum: ["user", "assistant"] }).notNull(),
  content: text("content").notNull(),
  citations: jsonb("citations").$type<Citation[]>().default([]),
  confidence: text("confidence", { enum: ["high", "moderate", "low"] }),
  createdAt: timestamp("created_at").defaultNow().notNull(),
});

export type TriageSession = typeof triageSessions.$inferSelect;
export type TriageMessage = typeof triageMessages.$inferSelect;
