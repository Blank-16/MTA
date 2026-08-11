import { Badge } from "@/components/ui/badge";
import type { TriageResponse } from "@/lib/validations/triage";

interface Props {
  confidence: TriageResponse["confidence"];
}

const CONFIDENCE_STYLES: Record<TriageResponse["confidence"], string> = {
  high: "bg-green-100 text-green-800 border-green-200",
  moderate: "bg-yellow-100 text-yellow-800 border-yellow-200",
  low: "bg-red-100 text-red-800 border-red-200",
};

export function ConfidenceBadge({ confidence }: Props) {
  return (
    <Badge variant="outline" className={CONFIDENCE_STYLES[confidence]}>
      {confidence} confidence
    </Badge>
  );
}
