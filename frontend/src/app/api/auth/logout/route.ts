import { NextRequest } from "next/server";
export const runtime = "nodejs";
const UPSTREAM_TIMEOUT_MS = 10000;
export async function POST(req: NextRequest) {
  const backendUrl = process.env.BACKEND_URL;
  const internalApiKey = process.env.INTERNAL_API_KEY;
  if (!backendUrl || !internalApiKey) return Response.json({ error: "Service misconfigured" }, { status: 500 });
  // Extract only the refresh_token cookie
  const allCookies = req.headers.get("cookie") ?? "";
  const refreshMatch = allCookies.match(/(?:^|;\s*)refresh_token=([^;]*)/);
  const cookieHeader = refreshMatch ? `refresh_token=${refreshMatch[1]}` : "";
  try {
    await fetch(`${backendUrl}/v1/auth/logout`, {
      method: "POST",
      headers: { "x-internal-key": internalApiKey, Cookie: cookieHeader },
    });
  } catch { /* best-effort logout */ }
  const response = new Response(null, { status: 204 });
  response.headers.set("set-cookie", "refresh_token=; Path=/; HttpOnly; Max-Age=0; SameSite=Lax");
  return response;
}
