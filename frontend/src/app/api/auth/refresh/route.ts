import { NextRequest } from "next/server";
export const runtime = "nodejs";
const UPSTREAM_TIMEOUT_MS = 10000;
export async function POST(req: NextRequest) {
  const backendUrl = process.env.BACKEND_URL;
  const internalApiKey = process.env.INTERNAL_API_KEY;
  if (!backendUrl || !internalApiKey) return Response.json({ error: "Service misconfigured" }, { status: 500 });
  // FIX: forward only the refresh_token cookie — not all cookies
  const allCookies = req.headers.get("cookie") ?? "";
  const refreshMatch = allCookies.match(/(?:^|;\s*)refresh_token=([^;]*)/);
  const cookieHeader = refreshMatch ? `refresh_token=${refreshMatch[1]}` : "";
  const _ctrl = new AbortController();
  setTimeout(() => _ctrl.abort(), UPSTREAM_TIMEOUT_MS);
  let upstream: Response;
  try {
    upstream = await fetch(`${backendUrl}/v1/auth/refresh`, {
      method: "POST",
      headers: { "x-internal-key": internalApiKey, Cookie: cookieHeader },
      signal: _ctrl.signal,
    });
  } catch (err) {
    console.error("[auth/refresh] Backend unreachable:", err);
    return Response.json({ error: "Service unavailable" }, { status: 503 });
  }
  const data = await upstream.text();
  const response = new Response(data, { status: upstream.status, headers: { "Content-Type": "application/json" } });
  const setCookie = upstream.headers.get("set-cookie");
  if (setCookie) response.headers.set("set-cookie", setCookie);
  return response;
}
