import { redirect } from "next/navigation";

// Server component — runs at request time, never ships to client
async function fetchAuditEntries(limit = 50) {
  const backendUrl = process.env.BACKEND_URL;
  const internalApiKey = process.env.INTERNAL_API_KEY;

  if (!backendUrl || !internalApiKey) {
    throw new Error("Missing service configuration");
  }

  const res = await fetch(`${backendUrl}/v1/admin/audit?limit=${limit}&escalated_only=false`, {
    headers: { "x-internal-key": internalApiKey },
    cache: "no-store",
  });

  if (res.status === 403) redirect("/login");
  if (!res.ok) throw new Error(`Audit fetch failed: ${res.status}`);
  return res.json() as Promise<AuditEntry[]>;
}

interface AuditEntry {
  id: string;
  session_id: string;
  role: string;
  confidence: string | null;
  restriction_log: Record<string, unknown>;
  created_at: string;
  escalated: boolean;
  escalation_reason: string | null;
}

export default async function AuditPage() {
  let entries: AuditEntry[] = [];
  let fetchError: string | null = null;

  try {
    entries = await fetchAuditEntries();
  } catch (err) {
    fetchError = err instanceof Error ? err.message : "Failed to load audit log";
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-6">
      <h1 className="text-xl font-semibold">Audit Log</h1>

      {fetchError && (
        <p className="rounded border border-destructive bg-destructive/10 px-4 py-2 text-sm text-destructive">
          {fetchError}
        </p>
      )}

      <div className="overflow-x-auto rounded border">
        <table className="w-full text-sm">
          <thead className="border-b bg-muted/50">
            <tr>
              {["ID", "Session", "Confidence", "Escalated", "Restriction", "Timestamp"].map((h) => (
                <th key={h} className="px-4 py-2 text-left font-medium text-muted-foreground">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {entries.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">
                  No entries found
                </td>
              </tr>
            )}
            {entries.map((entry) => (
              <tr key={entry.id} className="border-b last:border-0 hover:bg-muted/30">
                <td className="px-4 py-2 font-mono text-xs">{entry.id.slice(0, 8)}&hellip;</td>
                <td className="px-4 py-2 font-mono text-xs">{entry.session_id.slice(0, 8)}&hellip;</td>
                <td className="px-4 py-2">{entry.confidence ?? "—"}</td>
                <td className="px-4 py-2">
                  {entry.escalated ? (
                    <span className="text-destructive font-medium">Yes</span>
                  ) : (
                    <span className="text-muted-foreground">No</span>
                  )}
                </td>
                <td className="px-4 py-2 font-mono text-xs">
                  {(entry.restriction_log?.restriction_code as string) ?? "—"}
                </td>
                <td className="px-4 py-2 text-muted-foreground">
                  {new Date(entry.created_at).toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
