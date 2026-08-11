"use client";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

interface IntakeValues {
  location: string;
  duration: string;
  severity: number;
  associated: string;
  freeText: string;
}

interface Props {
  onSubmit: (message: string) => void;
}

const BODY_LOCATIONS = ["Head / Neck", "Chest", "Abdomen", "Back", "Arms / Hands", "Legs / Feet", "Skin", "General / Whole body"];
const DURATIONS = ["< 1 hour", "1–24 hours", "1–7 days", "1–4 weeks", "> 1 month"];

export function SymptomIntakeForm({ onSubmit }: Props) {
  const [values, setValues] = useState<IntakeValues>({
    location: "", duration: "", severity: 5, associated: "", freeText: "",
  });
  const [useForm, setUseForm] = useState(true);

  function buildMessage(v: IntakeValues): string {
    const parts: string[] = [];
    if (v.location) parts.push(`Location: ${v.location}`);
    if (v.duration) parts.push(`Duration: ${v.duration}`);
    parts.push(`Severity: ${v.severity}/10`);
    if (v.associated.trim()) parts.push(`Associated symptoms: ${v.associated.trim()}`);
    if (v.freeText.trim()) parts.push(`Additional details: ${v.freeText.trim()}`);
    return parts.join("\n");
  }

  function handleSubmit() {
    const msg = buildMessage(values);
    if (msg.trim()) onSubmit(msg);
  }

  if (!useForm) {
    return (
      <button
        onClick={() => setUseForm(true)}
        className="mx-auto mt-6 block text-xs text-muted-foreground underline underline-offset-2"
      >
        Use structured intake form
      </button>
    );
  }

  return (
    <div className="mx-auto mt-4 w-full max-w-lg rounded-xl border bg-card p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <p className="text-sm font-medium">Describe your symptoms</p>
        <button onClick={() => setUseForm(false)} className="text-xs text-muted-foreground hover:text-foreground">
          Free text instead
        </button>
      </div>

      <div className="space-y-4">
        {/* Body location */}
        <div className="space-y-1.5">
          <Label className="text-xs">Where is the problem?</Label>
          <div className="flex flex-wrap gap-1.5">
            {BODY_LOCATIONS.map((loc) => (
              <button
                key={loc}
                onClick={() => setValues((v) => ({ ...v, location: loc === v.location ? "" : loc }))}
                className={`rounded-full border px-2.5 py-0.5 text-xs transition-colors ${
                  values.location === loc
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border bg-background hover:bg-muted"
                }`}
              >
                {loc}
              </button>
            ))}
          </div>
        </div>

        {/* Duration */}
        <div className="space-y-1.5">
          <Label className="text-xs">How long have you had this?</Label>
          <div className="flex flex-wrap gap-1.5">
            {DURATIONS.map((d) => (
              <button
                key={d}
                onClick={() => setValues((v) => ({ ...v, duration: d === v.duration ? "" : d }))}
                className={`rounded-full border px-2.5 py-0.5 text-xs transition-colors ${
                  values.duration === d
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-border bg-background hover:bg-muted"
                }`}
              >
                {d}
              </button>
            ))}
          </div>
        </div>

        {/* Severity slider */}
        <div className="space-y-1.5">
          <Label className="text-xs">
            Severity: <span className="font-semibold">{values.severity}/10</span>
            <span className="ml-2 text-muted-foreground">
              {values.severity <= 3 ? "(mild)" : values.severity <= 6 ? "(moderate)" : "(severe)"}
            </span>
          </Label>
          <input
            type="range"
            min={1}
            max={10}
            value={values.severity}
            onChange={(e) => setValues((v) => ({ ...v, severity: Number(e.target.value) }))}
            className="h-1.5 w-full accent-primary"
          />
        </div>

        {/* Associated symptoms */}
        <div className="space-y-1.5">
          <Label className="text-xs">Any other symptoms? (optional)</Label>
          <input
            type="text"
            placeholder="e.g. nausea, fever, dizziness"
            value={values.associated}
            onChange={(e) => setValues((v) => ({ ...v, associated: e.target.value }))}
            className="w-full rounded-md border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            maxLength={200}
          />
        </div>

        {/* Free text addition */}
        <div className="space-y-1.5">
          <Label className="text-xs">Anything else to add? (optional)</Label>
          <Textarea
            placeholder="Any relevant medical history, medications, or context..."
            value={values.freeText}
            onChange={(e) => setValues((v) => ({ ...v, freeText: e.target.value }))}
            className="min-h-[60px] resize-none text-sm"
            maxLength={500}
          />
        </div>

        <Button
          onClick={handleSubmit}
          className="w-full"
          disabled={!values.location && !values.freeText.trim()}
        >
          Send
        </Button>
      </div>
    </div>
  );
}
