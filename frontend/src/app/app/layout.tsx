"use client";

import { Suspense, useEffect } from "react";
import { useRouter } from "next/navigation";
import { AppSidebar } from "@/components/app-sidebar";
import { Navbar } from "@/components/navbar";
import { useAuth } from "@/lib/auth-context";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const { user, isLoading } = useAuth();

  useEffect(() => {
    if (!isLoading && !user) {
      router.replace("/login");
    }
  }, [user, isLoading, router]);

  // Show nothing while we check auth state to prevent flash of protected content
  if (isLoading) {
    return (
      <div className="min-h-screen bg-black flex items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 rounded-full border-2 border-[#D99A45] border-t-transparent animate-spin" />
          <span className="text-xs text-[#71717A] font-mono">Loading…</span>
        </div>
      </div>
    );
  }

  // Redirect is in progress, render nothing
  if (!user) return null;

  return (
    <Suspense fallback={<div className="min-h-screen bg-black" />}>
      <div className="flex h-screen overflow-hidden bg-black text-white">
        <AppSidebar />
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          <Navbar />
          <main className="flex-1 overflow-y-auto p-4 md:p-6 lg:p-8">
            {children}
          </main>
        </div>
      </div>
    </Suspense>
  );
}
