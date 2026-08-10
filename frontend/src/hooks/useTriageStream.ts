"use client";
import { useCallback, useRef, useState } from "react";
import { TriageResponseSchema, type TriageResponse } from "@/lib/validations/triage";

export interface StreamingMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  streaming: boolean;
  response?: TriageResponse;
  error?: string;
}

interface UseTriageStreamResult {
  messages: StreamingMessage[];
  isStreaming: boolean;
  sendMessage: (text: string, sessionId: string, sessionToken: string) => Promise<void>;
  clearMessages: () => void;
  setMessages: React.Dispatch<React.SetStateAction<StreamingMessage[]>>;
}

export function useTriageStream(): UseTriageStreamResult {
  const [messages, setMessages] = useState<StreamingMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(async (
    text: string,
    sessionId: string,
    sessionToken: string,
  ) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    const userMsgId = crypto.randomUUID();
    const assistantMsgId = crypto.randomUUID();

    setMessages((prev) => [
      ...prev,
      { id: userMsgId, role: "user", content: text, streaming: false },
      { id: assistantMsgId, role: "assistant", content: "", streaming: true },
    ]);
    setIsStreaming(true);

    let response: Response;
    try {
      response = await fetch("/api/triage", {
        method: "POST",
        headers: { "Content-Type": "application/json", "x-session-token": sessionToken },
        body: JSON.stringify({ session_id: sessionId, message: text }),
        signal: controller.signal,
      });
    } catch (err) {
      if (!(err instanceof DOMException && err.name === "AbortError")) {
        _setError(setMessages, userMsgId, assistantMsgId, "Connection failed. Please try again.");
      }
      setIsStreaming(false);
      return;
    }

    // Auto-retry once on transient 503/504 (service unavailable / gateway timeout)
    if (response.status === 503 || response.status === 504) {
      await new Promise((r) => setTimeout(r, 1500));
      try {
        response = await fetch("/api/triage", {
          method: "POST",
          headers: { "Content-Type": "application/json", "x-session-token": sessionToken },
          body: JSON.stringify({ session_id: sessionId, message: text }),
          signal: controller.signal,
        });
      } catch { /* use original error response */ }
    }

    if (!response.ok) {
      let detail = "Request could not be processed.";
      try {
        const body = await response.json();
        detail = (typeof body?.detail === "string" ? body.detail : null) ?? body?.error ?? detail;
      } catch { /* ignore */ }
      if (response.status === 429) detail = "Too many requests. Please wait a moment.";
      if (response.status === 503 || response.status === 504) detail = "Service temporarily unavailable. Please try again.";
      if (response.status === 401 || response.status === 403) detail = "Session expired. Please refresh.";
      _setError(setMessages, userMsgId, assistantMsgId, detail);
      setIsStreaming(false);
      return;
    }

    const reader = response.body?.getReader();
    if (!reader) {
      _setError(setMessages, userMsgId, assistantMsgId, "Stream unavailable.");
      setIsStreaming(false);
      return;
    }

    const decoder = new TextDecoder();
    // FIX: buffer across network chunks — SSE events are \n\n-delimited.
    // A single read() call often returns partial events or multiple events joined.
    let lineBuffer = "";

    try {
      outer: while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        lineBuffer += decoder.decode(value, { stream: true });

        // FIX: split on \n\n (SSE event boundary), not \n
        const parts = lineBuffer.split("\n\n");
        // Last element is a partial event — keep it in the buffer
        lineBuffer = parts.pop() ?? "";

        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith("data: ")) continue;
          const payload = line.slice(6).trim();
          if (payload === "[DONE]") break outer;

          let event: Record<string, unknown>;
          try { event = JSON.parse(payload); } catch { continue; }

          if (event.type === "token" && typeof event.content === "string") {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantMsgId
                  ? { ...m, content: m.content + event.content }
                  : m,
              ),
            );
          } else if (event.type === "result") {
            const parsed = TriageResponseSchema.safeParse(event.data);
            if (parsed.success) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantMsgId
                    ? { ...m, content: parsed.data.summary, streaming: false, response: parsed.data }
                    : m,
                ),
              );
            }
          } else if (event.type === "error") {
            const detail = (event.detail as string | undefined) ?? "Response blocked by safety filter.";
            _setError(setMessages, userMsgId, assistantMsgId, detail);
          }
        }
      }
    } catch (err) {
      if (!(err instanceof DOMException && err.name === "AbortError")) {
        _setError(setMessages, userMsgId, assistantMsgId, "Stream interrupted.");
      }
    } finally {
      reader.releaseLock();
      setMessages((prev) =>
        prev.map((m) => (m.id === assistantMsgId ? { ...m, streaming: false } : m)),
      );
      setIsStreaming(false);
    }
  }, []);

  const clearMessages = useCallback(() => {
    abortRef.current?.abort();
    setMessages([]);
  }, []);

  return { messages, isStreaming, sendMessage, clearMessages, setMessages };
}

function _setError(
  setMessages: React.Dispatch<React.SetStateAction<StreamingMessage[]>>,
  userMsgId: string,
  assistantMsgId: string,
  error: string,
) {
  setMessages((prev) =>
    prev
      .filter((m) => m.id !== userMsgId)
      .map((m) =>
        m.id === assistantMsgId ? { ...m, content: "", streaming: false, error } : m,
      ),
  );
}
