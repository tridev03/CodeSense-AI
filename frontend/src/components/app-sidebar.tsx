"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ChevronLeft, ChevronRight, LayoutDashboard, Database, MessageSquare, Search, LogOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth-context";

const sidebarLinks = [
  { label: "Dashboard", href: "/app", icon: LayoutDashboard },
  { label: "Repositories", href: "/app/repositories", icon: Database },
  { label: "Chat", href: "/app/chat", icon: MessageSquare },
  { label: "Search", href: "/app/search/placeholder", icon: Search },
];

export function AppSidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { logout, user } = useAuth();
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isMounted, setIsMounted] = useState(false);

  useEffect(() => {
    setIsMounted(true);
    const stored = localStorage.getItem("sidebar_collapsed");
    if (stored) setIsCollapsed(JSON.parse(stored));
  }, []);

  const toggleCollapse = () => {
    const newVal = !isCollapsed;
    setIsCollapsed(newVal);
    localStorage.setItem("sidebar_collapsed", JSON.stringify(newVal));
  };

  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  if (!isMounted) return null;

  return (
    <aside
      className={`hidden md:flex flex-col h-screen bg-surface-2 border-r border-[#242424] transition-all duration-300 ${
        isCollapsed ? "w-16" : "w-60"
      }`}
    >
      {/* Sidebar Header */}
      <div className="h-14 flex items-center justify-between px-4 border-b border-[#242424]">
        {!isCollapsed && <span className="font-semibold text-white truncate">Menu</span>}
      </div>

      {/* Nav Links */}
      <nav className="flex-1 py-4 flex flex-col gap-2 px-2 overflow-y-auto">
        {sidebarLinks.map((link) => {
          const isActive = pathname === link.href || pathname.startsWith(link.href + "/");
          return (
            <Link
              key={link.label}
              href={link.href}
              className={`flex items-center gap-3 px-3 py-2 rounded-md transition-colors ${
                isActive
                  ? "bg-amber/10 text-amber"
                  : "text-zinc-400 hover:text-white hover:bg-white/5"
              }`}
              title={isCollapsed ? link.label : undefined}
            >
              <link.icon className="w-5 h-5 shrink-0" />
              {!isCollapsed && <span className="text-sm font-medium truncate">{link.label}</span>}
            </Link>
          );
        })}
      </nav>

      {/* Bottom: user email + logout */}
      <div className="border-t border-[#242424] p-2 space-y-1">
        {!isCollapsed && user && (
          <div className="px-3 py-1.5 mb-1">
            <p className="text-[10px] text-[#52525B] uppercase tracking-wider font-medium">Signed in as</p>
            <p className="text-xs text-[#A1A1AA] truncate font-mono mt-0.5">{user.email}</p>
          </div>
        )}

        {/* Logout button */}
        <button
          onClick={handleLogout}
          title={isCollapsed ? "Sign Out" : undefined}
          className={`flex items-center gap-3 px-3 py-2 rounded-md w-full transition-colors text-zinc-400 hover:text-red-400 hover:bg-red-500/10 ${
            isCollapsed ? "justify-center" : ""
          }`}
        >
          <LogOut className="w-5 h-5 shrink-0" />
          {!isCollapsed && <span className="text-sm font-medium">Sign Out</span>}
        </button>

        {/* Toggle Button */}
        <Button
          variant="ghost"
          size="icon"
          onClick={toggleCollapse}
          className="w-full flex items-center justify-center text-zinc-400 hover:text-white"
        >
          {isCollapsed ? <ChevronRight className="w-5 h-5" /> : <ChevronLeft className="w-5 h-5" />}
        </Button>
      </div>
    </aside>
  );
}
