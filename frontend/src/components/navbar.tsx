"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Cpu, Menu, X, LogOut, User } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useBackendStatus } from "@/hooks/use-backend-status";
import { Tooltip, TooltipTrigger, TooltipContent } from "@/components/ui/tooltip";
import { useAuth } from "@/lib/auth-context";

const navLinks = [
  { label: "Dashboard", href: "/app/repositories" },
  { label: "Repositories", href: "/app/repositories" },
  { label: "Settings", href: "/app/settings" },
];

export function Navbar() {
  const pathname = usePathname();
  const router = useRouter();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  const { isOnline, health, services } = useBackendStatus();
  const { user, logout } = useAuth();

  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  return (
    <header className="sticky top-0 z-50 w-full h-14 border-b border-[#242424] bg-black/60 backdrop-blur-md">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 h-full flex items-center justify-between">
        {/* Left: Logo */}
        <Link href="/" className="flex items-center gap-2.5 group">
          <div className="w-8 h-8 rounded-lg bg-[#141414] border border-[#242424] flex items-center justify-center text-[#D99A45] group-hover:border-[#D99A45]/40 transition-colors">
            <Cpu className="w-4 h-4" />
          </div>
          <span className="text-[#F5F5F5] font-light text-base tracking-tight">
            CodeSense <span className="text-[#D99A45] font-normal">AI</span>
          </span>
        </Link>

        {/* Center: Desktop Nav */}
        <nav className="hidden md:flex items-center gap-6">
          {navLinks.map((link) => (
            <Link
              key={link.label}
              href={link.href}
              className={`text-xs font-medium transition-colors hover:text-[#D99A45] ${
                pathname === link.href ? "text-[#D99A45]" : "text-[#A1A1AA]"
              }`}
            >
              {link.label}
            </Link>
          ))}
        </nav>

        {/* Right: Auth & Live Status */}
        <div className="hidden md:flex items-center gap-3">
          {/* Live Status Indicator */}
          <Tooltip>
            <TooltipTrigger className="flex items-center gap-2 px-2.5 py-1 rounded-full bg-[#101010] border border-[#242424] hover:border-[#383838] transition-colors cursor-pointer text-left">
              <span
                className={`w-2 h-2 rounded-full ${
                  health === "connected"
                    ? "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.7)] animate-pulse"
                    : health === "degraded"
                    ? "bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.7)]"
                    : "bg-red-500/80"
                }`}
              />
              <span className="text-[11px] font-mono text-[#A1A1AA]">
                {health === "connected"
                  ? "Live"
                  : health === "degraded"
                  ? "Degraded"
                  : "Offline"}
              </span>
            </TooltipTrigger>
            <TooltipContent className="bg-[#141414] border border-[#242424] text-[#F5F5F5] p-3 space-y-1.5 text-xs shadow-2xl rounded-xl z-50">
              <div className="font-semibold text-[#D99A45] border-b border-[#242424] pb-1">
                Backend Services
              </div>
              <div className="flex justify-between gap-5 text-[11px]">
                <span className="text-[#A1A1AA]">API Server:</span>
                <span className={isOnline ? "text-emerald-400 font-mono" : "text-red-400 font-mono"}>
                  {isOnline ? "Online" : "Offline"}
                </span>
              </div>
              <div className="flex justify-between gap-5 text-[11px]">
                <span className="text-[#A1A1AA]">PostgreSQL:</span>
                <span
                  className={
                    services?.database === "ok"
                      ? "text-emerald-400 font-mono"
                      : "text-amber-400 font-mono"
                  }
                >
                  {services?.database || "Unknown"}
                </span>
              </div>
              <div className="flex justify-between gap-5 text-[11px]">
                <span className="text-[#A1A1AA]">Qdrant Vector DB:</span>
                <span
                  className={
                    services?.qdrant === "ok"
                      ? "text-emerald-400 font-mono"
                      : "text-amber-400 font-mono"
                  }
                >
                  {services?.qdrant || "Unknown"}
                </span>
              </div>
              <div className="flex justify-between gap-5 text-[11px]">
                <span className="text-[#A1A1AA]">Redis:</span>
                <span className="text-[#A1A1AA] font-mono">
                  {services?.redis || "not_configured"}
                </span>
              </div>
            </TooltipContent>
          </Tooltip>

          {/* Auth section — show user email + logout if logged in, else Sign In */}
          {user ? (
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[#101010] border border-[#242424]">
                <User className="w-3 h-3 text-[#D99A45]" />
                <span className="text-[11px] font-mono text-[#A1A1AA] max-w-[120px] truncate">
                  {user.email}
                </span>
              </div>
              <button
                onClick={handleLogout}
                className="flex items-center gap-1.5 text-xs font-medium text-[#A1A1AA] hover:text-red-400 transition-colors px-2 py-1.5 rounded-lg hover:bg-red-500/10"
                title="Sign out"
              >
                <LogOut className="w-3.5 h-3.5" />
                <span className="hidden lg:inline">Sign Out</span>
              </button>
            </div>
          ) : (
            <>
              <Link
                href="/login"
                className="text-xs font-medium text-[#A1A1AA] hover:text-[#D99A45] transition-colors px-3 py-1.5"
              >
                Sign In
              </Link>
              <Link href="/app/repositories">
                <Button className="bg-[#D99A45] hover:bg-[#D99A45]/90 text-black text-xs font-medium h-8 px-3.5 rounded-xl transition-all shadow-md shadow-[#D99A45]/10">
                  Open App
                </Button>
              </Link>
            </>
          )}
        </div>

        {/* Mobile: Burger */}
        <button
          className="md:hidden p-2 text-[#A1A1AA] hover:text-white"
          onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
        >
          {isMobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>
      </div>

      {/* Mobile Menu */}
      {isMobileMenuOpen && (
        <div className="md:hidden absolute top-14 left-0 w-full bg-[#0D0D0D] border-b border-[#242424] p-5 flex flex-col gap-4 shadow-2xl">
          {navLinks.map((link) => (
            <Link
              key={link.label}
              href={link.href}
              className={`text-sm font-medium ${
                pathname === link.href ? "text-[#D99A45]" : "text-[#A1A1AA]"
              }`}
              onClick={() => setIsMobileMenuOpen(false)}
            >
              {link.label}
            </Link>
          ))}
          <div className="flex flex-col gap-2 pt-4 border-t border-[#1C1C1C]">
            {user ? (
              <>
                <div className="flex items-center gap-2 text-xs text-[#A1A1AA] py-1">
                  <User className="w-3.5 h-3.5 text-[#D99A45]" />
                  <span className="truncate">{user.email}</span>
                </div>
                <button
                  onClick={() => { handleLogout(); setIsMobileMenuOpen(false); }}
                  className="flex items-center gap-2 text-sm font-medium text-red-400 hover:text-red-300 py-2"
                >
                  <LogOut className="w-4 h-4" />
                  Sign Out
                </button>
              </>
            ) : (
              <>
                <Link
                  href="/login"
                  className="text-sm font-medium text-[#A1A1AA] hover:text-[#D99A45] py-2"
                  onClick={() => setIsMobileMenuOpen(false)}
                >
                  Sign In
                </Link>
                <Link href="/app/repositories" onClick={() => setIsMobileMenuOpen(false)}>
                  <Button className="bg-[#D99A45] text-black w-full justify-center text-xs h-9 rounded-xl">
                    Open App
                  </Button>
                </Link>
              </>
            )}
          </div>
        </div>
      )}
    </header>
  );
}
