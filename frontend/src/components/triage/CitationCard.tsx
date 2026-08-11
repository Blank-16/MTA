import { Badge } from "@/components/ui/badge";
import type { Citation } from "@/lib/validations/triage";

interface Props {
  citations: Citation[];
}

export function CitationCard({ citations }: Props) {
  if (citations.length === 0) return null;

  return (
    <div className="mt-2 space-y-1 border-l-2 border-muted pl-3">
      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">Sources</p>
      {citations.map((c, i) => (
        <div key={i} className="flex items-center gap-2 text-xs">
          <Badge variant="secondary">{c.source}</Badge>
          <span className="truncate text-muted-foreground">{c.section}</span>
          <span className="ml-auto tabular-nums text-muted-foreground">
            {(c.similarity * 100).toFixed(0)}%
          </span>
        </div>
      ))}
    </div>
  );
}
