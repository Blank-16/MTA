"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Stethoscope, LogOut, User } from "lucide-react";
import { useAuthStore } from "@/stores/authStore";
import { Button } from "@/components/ui/button";
import { useSessionStore } from "@/stores/sessionStore";

export function Navbar() {
  const router = useRouter();
  const { isAuthenticated, clearAuth } = useAuthStore();
  const { clearSession } = useSessionStore();

  async function handleLogout() {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } catch { /* best-effort */ }
    clearAuth();
    clearSession();
    router.push("/login");
  }

  return (
    <header className="border-b bg-background">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4">
        <Link href="/triage" className="flex items-center gap-2 font-semibold">
          <Stethoscope className="h-5 w-5 text-primary" />
          <span>MedTriage</span>
        </Link>
        <nav className="flex items-center gap-2 text-sm">
          {isAuthenticated ? (
            <>
              <span className="flex items-center gap-1 text-xs text-muted-foreground">
                <User className="h-3.5 w-3.5" /> Signed in
              </span>
              <Button variant="ghost" size="sm" onClick={handleLogout}>
                <LogOut className="mr-1.5 h-3.5 w-3.5" /> Sign out
              </Button>
            </>
          ) : (
            <>
              <Link href="/login">
                <Button variant="ghost" size="sm">Sign in</Button>
              </Link>
              <Link href="/register">
                <Button size="sm">Register</Button>
              </Link>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}
