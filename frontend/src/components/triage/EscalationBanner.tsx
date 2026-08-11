import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { TriangleAlert } from "lucide-react";

interface Props {
  reason: string;
}

export function EscalationBanner({ reason }: Props) {
  return (
    <Alert variant="destructive" className="border-destructive bg-destructive/10">
      <TriangleAlert className="h-4 w-4" />
      <AlertTitle>Seek immediate medical attention</AlertTitle>
      <AlertDescription>
        {reason} — Call emergency services (112 / 911) or go to your nearest A&E immediately.
      </AlertDescription>
    </Alert>
  );
}
