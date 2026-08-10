import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { Navbar } from "@/components/layout/Navbar";
import { DisclaimerFooter } from "@/components/layout/DisclaimerFooter";
import { ClientInit } from "@/components/layout/ClientInit";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Medical Triage Assistant",
  description: "AI-powered symptom guidance grounded in clinical guidelines",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={inter.className}>
        <div className="flex min-h-screen flex-col">
          <ClientInit />
          <Navbar />
          <main className="flex-1">{children}</main>
          <DisclaimerFooter />
        </div>
      </body>
    </html>
  );
}
