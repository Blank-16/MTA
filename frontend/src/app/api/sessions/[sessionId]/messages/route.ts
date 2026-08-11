import { NextRequest } from "next/server";

export const runtime = "nodejs";

export async function GET(
  req: NextRequest,
  context: { params: Promise<{ sessionId: string }> },
) {
  const { sessionId } = await context.params;

  const backendUrl = process.env.BACKEND_URL;
  const internalApiKey = process.env.INTERNAL_API_KEY;
  if (!backendUrl || !internalApiKey) {
    return Response.json({ error: "Service misconfigured" }, { status: 500 });
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${backendUrl}/v1/sessions/${sessionId}/messages`, {
      headers: {
        "x-internal-key": internalApiKey,
        "x-session-token": req.headers.get("x-session-token") ?? "",
      },
    });
  } catch (err) {
    console.error("[session messages route] Backend unreachable:", err);
    return Response.json({ error: "Service temporarily unavailable" }, { status: 503 });
  }

  const data = await upstream.text();
  return new Response(data, {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}
