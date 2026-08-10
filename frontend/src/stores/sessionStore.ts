"use client";
import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

interface SessionState {
  sessionId: string | null;
  sessionToken: string | null;
  setSession: (id: string, token: string) => void;
  clearSession: () => void;
}

export const useSessionStore = create<SessionState>()(
  persist(
    (set) => ({
      sessionId: null,
      sessionToken: null,
      setSession: (sessionId, sessionToken) => set({ sessionId, sessionToken }),
      clearSession: () => set({ sessionId: null, sessionToken: null }),
    }),
    {
      name: "triage-session",
      storage: createJSONStorage(() => sessionStorage),
      partialize: (state) => ({ sessionId: state.sessionId, sessionToken: state.sessionToken }),
      skipHydration: true,
    },
  ),
);

/**
 * Call this once on the client (e.g. in a root layout useEffect or a ClientInit component).
 * Required because skipHydration=true prevents automatic rehydration from sessionStorage —
 * without this call, sessionId/sessionToken are always null after a page load.
 */
export function rehydrateSessionStore(): void {
  void useSessionStore.persist.rehydrate();
}
