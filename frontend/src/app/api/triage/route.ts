import { NextRequest } from "next/server";
import { TriageRequestSchema } from "@/lib/validations/triage";

export const runtime = "nodejs";

// 30s timeout matches typical LLM p99 latency; prevents indefinite hang on model spike
const UPSTREAM_TIMEOUT_MS = 30_000;

export async function POST(req: NextRequest) {
  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return Response.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const parsed = TriageRequestSchema.safeParse(body);
  if (!parsed.success) {
    return Response.json({ error: parsed.error.flatten() }, { status: 422 });
  }

  const backendUrl = process.env.BACKEND_URL;
  const internalApiKey = process.env.INTERNAL_API_KEY;

  if (!backendUrl || !internalApiKey) {
    console.error("[triage route] Missing BACKEND_URL or INTERNAL_API_KEY");
    return Response.json({ error: "Service misconfigured" }, { status: 500 });
  }

  // FIX: AbortController timeout — prevents hanging requests on LLM latency spikes
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), UPSTREAM_TIMEOUT_MS);

  let upstream: Response;
  try {
    upstream = await fetch(`${backendUrl}/v1/triage`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-internal-key": internalApiKey,
        "x-session-token": req.headers.get("x-session-token") ?? "",
        "x-request-id": req.headers.get("x-request-id") ?? crypto.randomUUID(),
      },
      body: JSON.stringify(parsed.data),
      signal: controller.signal,
    });
  } catch (err) {
    clearTimeout(timeoutId);
    if (err instanceof Error && err.name === "AbortError") {
      console.error("[triage route] Upstream timeout after %dms", UPSTREAM_TIMEOUT_MS);
      return Response.json({ error: "Request timed out. Please try again." }, { status: 504 });
    }
    console.error("[triage route] Backend unreachable:", err);
    return Response.json({ error: "Service temporarily unavailable" }, { status: 503 });
  }

  clearTimeout(timeoutId);

  if (!upstream.ok) {
    const errorBody = await upstream.text();
    return new Response(errorBody, {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
  }

  return new Response(upstream.body, {
    status: 200,
    headers: {
      "Content-Type": upstream.headers.get("Content-Type") ?? "application/json",
      "Cache-Control": "no-store",
      "X-Request-ID": upstream.headers.get("x-request-id") ?? "",
    },
  });
}
