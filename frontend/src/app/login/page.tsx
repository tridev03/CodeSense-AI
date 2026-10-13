"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { toast } from "sonner";
import { Cpu, ArrowRight, Loader2, Lock, Mail } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function LoginPage() {
  const router = useRouter();
  const { user, login, isLoading } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    if (!isLoading && user) {
      router.replace("/app");
    }
  }, [user, isLoading, router]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) {
      toast.error("Please fill in all fields");
      return;
    }

    try {
      setIsSubmitting(true);
      await login(email, password);
      toast.success("Welcome back!");
      router.push("/app");
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : "Failed to sign in";
      toast.error(errorMsg);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="relative min-h-screen bg-black flex flex-col justify-center items-center px-4 overflow-hidden">
      {/* Amber radial glow */}
      <div
        className="pointer-events-none absolute inset-0 opacity-40"
        style={{
          background:
            "radial-gradient(ellipse 60% 50% at 50% 60%, rgba(217,154,69,0.15) 0%, transparent 70%)",
        }}
      />

      <div className="relative z-10 w-full max-w-md">
        {/* Brand header */}
        <div className="text-center mb-8">
          <Link
            href="/"
            className="inline-flex items-center gap-2.5 group transition-transform active:scale-95"
          >
            <div className="w-10 h-10 rounded-xl bg-[#141414] border border-[#303030] flex items-center justify-center text-[#D99A45] group-hover:border-[#D99A45]/50 transition-colors">
              <Cpu className="w-5 h-5" />
            </div>
            <span className="text-xl font-light tracking-tight text-[#F5F5F5]">
              CodeSense <span className="text-[#D99A45] font-normal">AI</span>
            </span>
          </Link>
          <h1 className="mt-6 text-2xl font-light tracking-tight text-[#F5F5F5]">
            Sign in to your account
          </h1>
          <p className="mt-2 text-sm text-[#71717A]">
            Access your codebase knowledge and autonomous agents
          </p>
        </div>

        {/* Card */}
        <div className="bg-[#0D0D0D] border border-[#242424] rounded-2xl p-7 shadow-2xl backdrop-blur-xl relative">
          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="space-y-2">
              <Label htmlFor="email" className="text-xs text-[#A1A1AA] uppercase tracking-wider">
                Email Address
              </Label>
              <div className="relative">
                <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-[#71717A]" />
                <Input
                  id="email"
                  type="email"
                  placeholder="developer@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="pl-10 bg-[#080808] border-[#242424] text-[#F5F5F5] placeholder:text-[#52525B] focus:border-[#D99A45] focus:ring-[#D99A45]/20 h-11 rounded-xl"
                  required
                />
              </div>
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <Label htmlFor="password" className="text-xs text-[#A1A1AA] uppercase tracking-wider">
                  Password
                </Label>
              </div>
              <div className="relative">
                <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-[#71717A]" />
                <Input
                  id="password"
                  type="password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="pl-10 bg-[#080808] border-[#242424] text-[#F5F5F5] placeholder:text-[#52525B] focus:border-[#D99A45] focus:ring-[#D99A45]/20 h-11 rounded-xl"
                  required
                />
              </div>
            </div>

            <Button
              type="submit"
              disabled={isSubmitting}
              className="w-full bg-[#D99A45] hover:bg-[#D99A45]/90 text-black font-medium h-11 rounded-xl transition-all shadow-lg shadow-[#D99A45]/10 mt-2"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Signing in...
                </>
              ) : (
                <>
                  Sign In
                  <ArrowRight className="w-4 h-4 ml-2" />
                </>
              )}
            </Button>
          </form>

          <div className="mt-6 pt-6 border-t border-[#1C1C1C] text-center">
            <p className="text-xs text-[#71717A]">
              Don&apos;t have an account?{" "}
              <Link
                href="/register"
                className="text-[#D99A45] hover:underline font-medium ml-1"
              >
                Create one now
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

