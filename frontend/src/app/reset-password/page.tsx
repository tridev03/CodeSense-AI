"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { Cpu, ArrowLeft, Loader2, Lock, Mail, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export default function ResetPasswordPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!email || !newPassword || !confirmPassword) {
      toast.error("Please fill in all fields.");
      return;
    }

    if (newPassword.length < 8) {
      toast.error("Password must be at least 8 characters long.");
      return;
    }

    if (newPassword !== confirmPassword) {
      toast.error("Passwords do not match.");
      return;
    }

    try {
      setIsSubmitting(true);
      const res = await fetch(`${API_BASE}/auth/reset-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email: email.trim(),
          new_password: newPassword,
        }),
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || "Failed to reset password.");
      }

      setIsSuccess(true);
      toast.success("Password reset successfully!");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to reset password.";
      toast.error(msg);
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
            Reset your password
          </h1>
          <p className="mt-2 text-sm text-[#71717A]">
            Enter your email and choose a new password
          </p>
        </div>

        {/* Card */}
        <div className="bg-[#0D0D0D] border border-[#242424] rounded-2xl p-7 shadow-2xl backdrop-blur-xl relative">
          {isSuccess ? (
            <div className="text-center py-6 space-y-4">
              <div className="w-12 h-12 rounded-full bg-emerald-500/10 border border-emerald-500/20 text-emerald-400 flex items-center justify-center mx-auto">
                <CheckCircle2 className="w-6 h-6" />
              </div>
              <h2 className="text-lg font-medium text-white">Password Updated</h2>
              <p className="text-xs text-[#71717A] max-w-xs mx-auto">
                Your password has been reset successfully. You can now log in with your new credentials.
              </p>
              <Button
                onClick={() => router.push("/login")}
                className="w-full bg-[#D99A45] hover:bg-[#D99A45]/90 text-black font-medium h-11 rounded-xl mt-4"
              >
                Go to Sign In
              </Button>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="email" className="text-xs text-[#A1A1AA] uppercase tracking-wider">
                  Account Email
                </Label>
                <div className="relative">
                  <Mail className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-[#71717A]" />
                  <Input
                    id="email"
                    type="email"
                    placeholder="developer@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="pl-10 bg-[#080808] border-[#242424] text-[#F5F5F5] placeholder:text-[#52525B] focus:border-[#D99A45] h-11 rounded-xl"
                    required
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="newPassword" className="text-xs text-[#A1A1AA] uppercase tracking-wider">
                  New Password
                </Label>
                <div className="relative">
                  <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-[#71717A]" />
                  <Input
                    id="newPassword"
                    type="password"
                    placeholder="•••••••• (min 8 chars)"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    className="pl-10 bg-[#080808] border-[#242424] text-[#F5F5F5] placeholder:text-[#52525B] focus:border-[#D99A45] h-11 rounded-xl"
                    required
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="confirmPassword" className="text-xs text-[#A1A1AA] uppercase tracking-wider">
                  Confirm Password
                </Label>
                <div className="relative">
                  <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-[#71717A]" />
                  <Input
                    id="confirmPassword"
                    type="password"
                    placeholder="••••••••"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    className="pl-10 bg-[#080808] border-[#242424] text-[#F5F5F5] placeholder:text-[#52525B] focus:border-[#D99A45] h-11 rounded-xl"
                    required
                  />
                </div>
              </div>

              <Button
                type="submit"
                disabled={isSubmitting}
                className="w-full bg-[#D99A45] hover:bg-[#D99A45]/90 text-black font-medium h-11 rounded-xl transition-all shadow-lg shadow-[#D99A45]/10 mt-3"
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    Resetting Password...
                  </>
                ) : (
                  "Reset Password"
                )}
              </Button>
            </form>
          )}

          <div className="mt-6 pt-6 border-t border-[#1C1C1C] text-center">
            <Link
              href="/login"
              className="inline-flex items-center gap-1.5 text-xs text-[#71717A] hover:text-white transition-colors"
            >
              <ArrowLeft className="w-3.5 h-3.5" /> Back to Sign In
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}

