"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useSessionStore } from "@/stores/sessionStore";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { MessageSquare, Plus, Loader2 } from "lucide-react";

interface SessionSummary {
  id: string;
  created_at: string;
  escalated: boolean;
}

export function SessionSidebar() {
  const router = useRouter();
  const { sessionId, sessionToken, setSession } = useSessionStore();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!sessionToken) return;

    // FIX: AbortController cancels stale fetch on remount / sessionToken change
    const controller = new AbortController();
    setLoading(true);

    fetch("/api/sessions", {
      headers: { "x-session-token": sessionToken },
      signal: controller.signal,
    })
      .then((r) => (r.ok ? r.json() : []))
      .then((data: SessionSummary[]) => setSessions(data))
      .catch((err) => {
        if (!(err instanceof DOMException && err.name === "AbortError")) {
          console.error("[SessionSidebar] fetch failed:", err);
        }
      })
      .finally(() => setLoading(false));

    return () => controller.abort();
  }, [sessionToken]);

  async function startNewSession() {
    try {
      const res = await fetch("/api/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!res.ok) return;
      const { session_id, session_token } = await res.json() as { session_id: string; session_token: string };
      setSession(session_id, session_token);
      router.push("/triage");
    } catch { /* ignore */ }
  }

  const formatDate = (iso: string) =>
    new Intl.DateTimeFormat(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(iso));

  return (
    <aside className="flex h-full w-56 flex-col border-r bg-muted/20">
      <div className="flex items-center justify-between border-b px-3 py-2">
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Sessions
        </span>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7"
          onClick={startNewSession}
          title="New session"
        >
          <Plus className="h-3.5 w-3.5" />
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto py-1">
        {loading && (
          <div className="flex justify-center py-4">
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          </div>
        )}

        {!loading && sessions.length === 0 && (
          <p className="px-3 py-4 text-xs text-muted-foreground">No past sessions</p>
        )}

        {sessions.map((s) => {
          const isActive = s.id === sessionId;
          return (
            <button
              key={s.id}
              onClick={() => {
                // FIX: guard against null token — empty string causes 403 on all requests
                if (sessionToken) {
                  setSession(s.id, sessionToken);
                  router.push(`/triage/${s.id}`);
                }
              }}
              disabled={!sessionToken}
              className={cn(
                "flex w-full items-start gap-2 px-3 py-2 text-left text-xs transition-colors hover:bg-muted disabled:opacity-50",
                isActive && "bg-muted",
              )}
            >
              <MessageSquare
                className={cn(
                  "mt-0.5 h-3 w-3 shrink-0",
                  s.escalated ? "text-destructive" : "text-muted-foreground",
                )}
              />
              <div className="min-w-0">
                <p className="truncate font-medium">{s.id.slice(0, 8)}&hellip;</p>
                <p className="text-muted-foreground">{formatDate(s.created_at)}</p>
                {s.escalated && <p className="text-destructive">Escalated</p>}
              </div>
            </button>
          );
        })}
      </div>
    </aside>
  );
}
