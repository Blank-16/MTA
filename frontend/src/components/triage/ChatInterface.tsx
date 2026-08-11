"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { AssistantBubble, UserBubble } from "./MessageBubble";
import { SymptomIntakeForm } from "./SymptomIntakeForm";
import { useSession } from "@/hooks/useSession";
import { useTriageStream } from "@/hooks/useTriageStream";
import { Loader2, SendHorizonal, AlertCircle, RefreshCw, Sparkles } from "lucide-react";

export function ChatInterface() {
  const { sessionId, sessionToken, loading: sessionLoading, error: sessionError, retry: retrySession } = useSession();
  const { messages, isStreaming, sendMessage, setMessages } = useTriageStream();
  const [input, setInput] = useState("");
  const [showIntake, setShowIntake] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isStreaming]);

  // Restore history from backend on session mount
  useEffect(() => {
    if (!sessionId || !sessionToken || messages.length > 0) return;
    let cancelled = false;

    fetch(`/api/sessions/${sessionId}/messages`, {
      headers: { "x-session-token": sessionToken },
    })
      .then((r) => r.ok ? r.json() : [])
      .then((rows: Array<{ id: string; role: "user" | "assistant"; content: string }>) => {
        if (!cancelled && rows.length > 0) {
          setMessages(rows.map((r) => ({ id: r.id, role: r.role, content: r.content, streaming: false })));
          setShowIntake(false);
        }
      })
      .catch(() => { /* non-fatal */ });

    return () => { cancelled = true; };
  }, [sessionId, sessionToken]); // eslint-disable-line react-hooks/exhaustive-deps

  const submit = useCallback(async (text?: string) => {
    const trimmed = (text ?? input).trim();
    if (!trimmed || !sessionId || !sessionToken || isStreaming) return;
    setInput("");
    setShowIntake(false);
    await sendMessage(trimmed, sessionId, sessionToken);
    textareaRef.current?.focus();
  }, [input, sessionId, sessionToken, isStreaming, sendMessage]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void submit(); }
    },
    [submit],
  );

  if (sessionLoading) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        <p className="text-sm text-muted-foreground">Starting session…</p>
      </div>
    );
  }

  if (sessionError) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3">
        <AlertCircle className="h-6 w-6 text-destructive" />
        <p className="text-sm text-destructive">{sessionError}</p>
        <Button variant="outline" size="sm" onClick={retrySession}>
          <RefreshCw className="mr-2 h-3.5 w-3.5" /> Retry
        </Button>
      </div>
    );
  }

  const canSubmit = input.trim().length > 0 && !isStreaming && !!sessionId;
  const isEmpty = messages.length === 0;

  return (
    <div className="flex h-full flex-col">
      {/* Message list */}
      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        {isEmpty && showIntake && (
          <SymptomIntakeForm onSubmit={(msg) => void submit(msg)} />
        )}

        {isEmpty && !showIntake && (
          <div className="mt-8 text-center">
            <p className="text-sm text-muted-foreground">Describe your symptoms below.</p>
            <button
              onClick={() => setShowIntake(true)}
              className="mt-2 flex items-center gap-1.5 mx-auto text-xs text-muted-foreground underline underline-offset-2"
            >
              <Sparkles className="h-3 w-3" /> Use guided intake form
            </button>
          </div>
        )}

        {messages.map((msg) => {
          if (msg.error) {
            return (
              <div key={msg.id} className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-3 py-2">
                <AlertCircle className="h-3.5 w-3.5 shrink-0 text-destructive" />
                <p className="text-sm text-destructive">{msg.error}</p>
              </div>
            );
          }
          if (msg.role === "user") return <UserBubble key={msg.id} content={msg.content} />;
          if (msg.role === "assistant") {
            return msg.response
              ? <AssistantBubble key={msg.id} response={msg.response} />
              : (
                <div key={msg.id} className="flex justify-start">
                  <div className="max-w-[85%] rounded-2xl rounded-tl-sm border bg-card px-4 py-3 shadow-sm">
                    {msg.streaming && !msg.content && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
                    {msg.content && <p className="text-sm leading-relaxed">{msg.content}</p>}
                    {msg.streaming && msg.content && (
                      <span className="inline-block h-3.5 w-0.5 animate-pulse bg-foreground align-middle ml-0.5" />
                    )}
                  </div>
                </div>
              );
          }
          return null;
        })}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="border-t bg-background p-4">
        <div className="flex items-end gap-2">
          <Textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Describe your symptoms…"
            className="min-h-[60px] resize-none"
            maxLength={2000}
            disabled={isStreaming || !sessionId}
            aria-label="Symptom description"
          />
          <Button
            type="button"
            size="icon"
            onClick={() => void submit()}
            disabled={!canSubmit}
            aria-label="Send message"
          >
            {isStreaming
              ? <Loader2 className="h-4 w-4 animate-spin" />
              : <SendHorizonal className="h-4 w-4" />
            }
          </Button>
        </div>
        <p
          className={`mt-1 text-right text-xs ${input.length > 1800 ? "text-destructive font-medium" : "text-muted-foreground"}`}
          aria-live="polite"
        >
          {input.length}/2000{input.length > 1800 ? ` (${2000 - input.length} remaining)` : ""}
        </p>
      </div>
    </div>
  );
}
