import { z } from "zod";

export const CitationSchema = z.object({
  source: z.string(),
  section: z.string(),
  similarity: z.number().min(0).max(1),
  jurisdiction: z.string(),
});

export const TriageRequestSchema = z.object({
  session_id: z.string().uuid(),
  message: z
    .string()
    .min(1, "Message cannot be empty")
    .max(2000, "Message cannot exceed 2000 characters")
    .transform((v) => v.trim()),
});

export const TriageResponseSchema = z.object({
  session_id: z.string().uuid(),
  message_id: z.string().uuid(),
  summary: z.string().min(1, "Summary cannot be empty"),
  citations: z.array(CitationSchema),
  escalate: z.boolean(),
  escalation_reason: z.string().nullable(),
  confidence: z.enum(["high", "moderate", "low"]),
  disclaimer: z.enum(["consult_gp", "emergency", "pharmacist"]),
  restriction_triggered: z.boolean(),
  restriction_code: z.string().nullable(),
});

export type Citation = z.infer<typeof CitationSchema>;
export type TriageRequest = z.infer<typeof TriageRequestSchema>;
export type TriageResponse = z.infer<typeof TriageResponseSchema>;

export const LoginSchema = z.object({
  email: z.string().email(),
  password: z.string().min(8, "Password must be at least 8 characters"),
});

export const RegisterSchema = LoginSchema.extend({
  confirmPassword: z.string(),
}).refine((d) => d.password === d.confirmPassword, {
  message: "Passwords do not match",
  path: ["confirmPassword"],
});

export type LoginInput = z.infer<typeof LoginSchema>;
export type RegisterInput = z.infer<typeof RegisterSchema>;
