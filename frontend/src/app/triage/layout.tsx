"use client";
import { SessionSidebar } from "@/components/layout/SessionSidebar";

export default function TriageLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-[calc(100vh-3.5rem)]">
      <SessionSidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        {children}
      </div>
    </div>
  );
}
