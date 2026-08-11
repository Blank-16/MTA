import { NextRequest } from "next/server";
export const runtime = "nodejs";

export async function GET(req: NextRequest) {
  const backendUrl = process.env.BACKEND_URL;
  const internalApiKey = process.env.INTERNAL_API_KEY;
  if (!backendUrl || !internalApiKey) return Response.json({ error: "Service misconfigured" }, { status: 500 });

  let upstream: Response;
  try {
    upstream = await fetch(`${backendUrl}/v1/sessions`, {
      headers: {
        "x-internal-key": internalApiKey,
        "x-session-token": req.headers.get("x-session-token") ?? "",
        Authorization: req.headers.get("authorization") ?? "",
      },
    });
  } catch (err) {
    console.error("[sessions route] Backend unreachable:", err);
    return Response.json({ error: "Service temporarily unavailable" }, { status: 503 });
  }

  const data = await upstream.text();
  return new Response(data, { status: upstream.status, headers: { "Content-Type": "application/json" } });
}

export async function POST(req: NextRequest) {
  const backendUrl = process.env.BACKEND_URL;
  const internalApiKey = process.env.INTERNAL_API_KEY;
  if (!backendUrl || !internalApiKey) return Response.json({ error: "Service misconfigured" }, { status: 500 });

  let body: Record<string, unknown> = { user_id: null };
  try {
    const parsed = await req.json();
    if (parsed && typeof parsed === "object") body = parsed as Record<string, unknown>;
  } catch { /* anonymous session */ }

  let upstream: Response;
  try {
    upstream = await fetch(`${backendUrl}/v1/sessions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-internal-key": internalApiKey,
      },
      body: JSON.stringify(body),
    });
  } catch (err) {
    console.error("[sessions route] Backend unreachable:", err);
    return Response.json({ error: "Service temporarily unavailable" }, { status: 503 });
  }

  const data = await upstream.text();
  return new Response(data, { status: upstream.status, headers: { "Content-Type": "application/json" } });
}
