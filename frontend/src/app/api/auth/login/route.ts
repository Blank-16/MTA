import { NextRequest } from "next/server";
export const runtime = "nodejs";
const UPSTREAM_TIMEOUT_MS = 10000;
export async function POST(req: NextRequest) {
  const backendUrl = process.env.BACKEND_URL;
  const internalApiKey = process.env.INTERNAL_API_KEY;
  if (!backendUrl || !internalApiKey) return Response.json({ error: "Service misconfigured" }, { status: 500 });
  let body: unknown;
  try { body = await req.json(); } catch { return Response.json({ error: "Invalid body" }, { status: 400 }); }
  const _ctrl = new AbortController();
  setTimeout(() => _ctrl.abort(), UPSTREAM_TIMEOUT_MS);
  let upstream: Response;
  try {
    upstream = await fetch(`${backendUrl}/v1/auth/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-internal-key": internalApiKey,
        "user-agent": req.headers.get("user-agent") ?? "",
        "x-forwarded-for": req.headers.get("x-forwarded-for") ?? "",
      },
      body: JSON.stringify(body),
      signal: _ctrl.signal,
    });
  } catch (err) {
    console.error("[auth/login] Backend unreachable:", err);
    return Response.json({ error: "Service unavailable" }, { status: 503 });
  }
  const data = await upstream.text();
  const response = new Response(data, { status: upstream.status, headers: { "Content-Type": "application/json" } });
  const setCookie = upstream.headers.get("set-cookie");
  if (setCookie) response.headers.set("set-cookie", setCookie);
  return response;
}
