import { z } from "zod";
import { TriageResponseSchema, type TriageResponse } from "@/lib/validations/triage";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function handleResponse<T>(res: Response, parser: (data: unknown) => T): Promise<T> {
  if (!res.ok) {
    let detail: unknown;
    try {
      detail = await res.json();
    } catch {
      detail = await res.text();
    }
    throw new ApiError(res.status, `HTTP ${res.status}`, detail);
  }
  const data = await res.json();
  return parser(data);
}

// FIX: runtime schema instead of unsafe cast
const SessionResponseSchema = z.object({
  session_id: z.string().uuid("Backend returned invalid session_id"),
  session_token: z.string().min(1, "Backend returned empty session_token"),
});

export type SessionResponse = z.infer<typeof SessionResponseSchema>;

export async function createSession(userId?: string): Promise<SessionResponse> {
  const res = await fetch("/api/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId ?? null }),
  });
  return handleResponse(res, (d) => SessionResponseSchema.parse(d));
}

export async function submitTriage(
  sessionId: string,
  message: string,
  sessionToken: string,
): Promise<TriageResponse> {
  const res = await fetch("/api/triage", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-session-token": sessionToken,
    },
    body: JSON.stringify({ session_id: sessionId, message }),
  });
  return handleResponse(res, (d) => TriageResponseSchema.parse(d));
}

export async function endSession(sessionId: string, sessionToken: string): Promise<void> {
  await fetch(`/api/sessions/${sessionId}`, {
    method: "DELETE",
    headers: { "x-session-token": sessionToken },
  });
}
