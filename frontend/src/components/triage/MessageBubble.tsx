import { cn } from "@/lib/utils";
import { CitationCard } from "./CitationCard";
import { ConfidenceBadge } from "./ConfidenceBadge";
import { EscalationBanner } from "./EscalationBanner";
import type { TriageResponse } from "@/lib/validations/triage";

interface UserBubbleProps {
  content: string;
}

interface AssistantBubbleProps {
  response: TriageResponse;
}

export function UserBubble({ content }: UserBubbleProps) {
  return (
    <div className="flex justify-end">
      <div className="max-w-[75%] rounded-2xl rounded-tr-sm bg-primary px-4 py-2.5 text-primary-foreground">
        <p className="text-sm leading-relaxed">{content}</p>
      </div>
    </div>
  );
}

// FIX: covers 112 (EU/international), 911 (US/Canada), 999 (UK)
const DISCLAIMER_TEXT: Record<TriageResponse["disclaimer"], string> = {
  consult_gp: "This is general information only. Please consult a qualified healthcare provider for personalised advice.",
  emergency: "If you or someone nearby is in immediate danger, call emergency services — 112, 911, or 999 — now.",
  pharmacist: "Speak with a pharmacist before taking any medication.",
};

export function AssistantBubble({ response }: AssistantBubbleProps) {
  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] space-y-3">
        {response.escalate && response.escalation_reason && (
          <EscalationBanner reason={response.escalation_reason} />
        )}

        <div className="rounded-2xl rounded-tl-sm border bg-card px-4 py-3 shadow-sm">
          <p className="text-sm leading-relaxed text-card-foreground">{response.summary}</p>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            <ConfidenceBadge confidence={response.confidence} />
          </div>

          {response.citations.length > 0 && (
            <CitationCard citations={response.citations} />
          )}

          {/* Non-dismissable compliance disclaimer — always rendered */}
          <p className="mt-3 border-t pt-2 text-xs text-muted-foreground">
            {DISCLAIMER_TEXT[response.disclaimer]}
          </p>
        </div>
      </div>
    </div>
  );
}
