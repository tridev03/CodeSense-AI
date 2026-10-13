"use client";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";

/**
 * /app root — redirect to /app/repositories if authenticated,
 * or to /login if not.
 */
export default function AppRoot() {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading) {
      router.replace(user ? "/app/repositories" : "/login");
    }
  }, [user, isLoading, router]);

  return (
    <div className="min-h-screen bg-black flex items-center justify-center">
      <span className="w-5 h-5 rounded-full border-2 border-[#D99A45] border-t-transparent animate-spin" />
    </div>
  );
}

