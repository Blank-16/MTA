import { ChatInterface } from "@/components/triage/ChatInterface";

export const metadata = { title: "Triage — MedTriage" };

export default function TriagePage() {
  return (
    <div className="flex h-full flex-col">
      <ChatInterface />
    </div>
  );
}
