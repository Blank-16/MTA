"use client";
import { useCallback, useEffect, useState } from "react";
import { useSessionStore } from "@/stores/sessionStore";
import { createSession, ApiError } from "@/lib/api";

interface UseSessionResult {
  sessionId: string | null;
  sessionToken: string | null;
  loading: boolean;
  error: string | null;
  // FIX: expose retry so callers can trigger re-creation on failure
  retry: () => void;
}

export function useSession(): UseSessionResult {
  const { sessionId, sessionToken, setSession, clearSession } = useSessionStore();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // retryCounter bumped by retry() to re-trigger the effect
  const [retryCount, setRetryCount] = useState(0);
  const retry = useCallback(() => {
    clearSession();
    setError(null);
    setRetryCount((c) => c + 1);
  }, [clearSession]);

  useEffect(() => {
    if (sessionId && sessionToken) return;

    // Use local flag per effect instance — avoids shared ref mutation between
    // rapid remounts where cleanup of run N and setup of run N+1 overlap
    let cancelled = false;
    setLoading(true);
    setError(null);

    createSession()
      .then(({ session_id, session_token }) => {
        if (!cancelled) setSession(session_id, session_token);
      })
      .catch((err) => {
        if (!cancelled) {
          const message =
            err instanceof ApiError
              ? `Session creation failed (HTTP ${err.status})`
              : "Failed to start session. Check your connection.";
          setError(message);
          console.error("[useSession]", err);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
    // retryCount in deps intentionally re-triggers the effect on manual retry
  }, [sessionId, sessionToken, setSession, retryCount]); // eslint-disable-line react-hooks/exhaustive-deps

  return { sessionId, sessionToken, loading, error, retry };
}
