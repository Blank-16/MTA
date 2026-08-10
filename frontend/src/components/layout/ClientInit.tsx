"use client";
import { useEffect } from "react";
import { rehydrateSessionStore } from "@/stores/sessionStore";

/**
 * Renders nothing. Triggers sessionStorage rehydration on the client after
 * the initial SSR render. Must be included in the root layout.
 *
 * Required because Zustand persist skipHydration=true prevents auto-rehydration
 * (which avoids SSR mismatch), so we trigger it manually after mount.
 */
export function ClientInit() {
  useEffect(() => {
    rehydrateSessionStore();
  }, []);

  return null;
}
