"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  ChevronLeft,
  ChevronRight,
  LayoutDashboard,
  MessageSquare,
  LogOut,
  Plus,
  Clock,
  Trash2,
  ChevronDown,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/lib/auth-context";

interface ChatHistoryItem {
  id: string;
  query: string;
  preview: string;
  timestamp: string;
  messages: any[];
}

export function AppSidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { logout, user } = useAuth();
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [isMounted, setIsMounted] = useState(false);

  // Recents / Chat history state
  const [chatHistory, setChatHistory] = useState<ChatHistoryItem[]>([]);
  const [isRecentsOpen, setIsRecentsOpen] = useState(true);

  const loadHistory = () => {
    try {
      const saved = localStorage.getItem("direct_chat_history_sessions");
      if (saved) {
        setChatHistory(JSON.parse(saved));
      } else {
        setChatHistory([]);
      }
    } catch {
      // Ignore parse errors
    }
  };

  useEffect(() => {
    setIsMounted(true);
    const stored = localStorage.getItem("sidebar_collapsed");
    if (stored) setIsCollapsed(JSON.parse(stored));

    loadHistory();

    // Listen for storage events or custom updates
    const handleStorageChange = () => loadHistory();
    window.addEventListener("storage", handleStorageChange);
    window.addEventListener("chat_history_updated", handleStorageChange);

    return () => {
      window.removeEventListener("storage", handleStorageChange);
      window.removeEventListener("chat_history_updated", handleStorageChange);
    };
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

  const handleSelectHistoryItem = (item: ChatHistoryItem) => {
    localStorage.setItem("active_direct_chat_session", JSON.stringify(item));
    window.dispatchEvent(new Event("load_active_chat_session"));
    router.push("/app/chat");
  };

  const handleNewChat = () => {
    localStorage.removeItem("active_direct_chat_session");
    window.dispatchEvent(new Event("start_new_chat_session"));
    router.push("/app/chat");
  };

  const handleClearHistory = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (confirm("Clear all chat history?")) {
      localStorage.removeItem("direct_chat_history_sessions");
      localStorage.removeItem("active_direct_chat_session");
      setChatHistory([]);
      window.dispatchEvent(new Event("chat_history_updated"));
      window.dispatchEvent(new Event("start_new_chat_session"));
    }
  };

  if (!isMounted) return null;

  const isChatActive = pathname === "/app/chat" || pathname.startsWith("/app/chat/");
  const isDashboardActive = pathname === "/app/repositories" || pathname === "/app";

  return (
    <aside
      className={`hidden md:flex flex-col h-screen bg-surface-2 border-r border-[#242424] transition-all duration-300 ${
        isCollapsed ? "w-16" : "w-64"
      }`}
    >
      {/* Sidebar Header */}
      <div className="h-14 flex items-center justify-between px-4 border-b border-[#242424]">
        {!isCollapsed && <span className="font-semibold text-white truncate text-sm">Menu</span>}
      </div>

      {/* Nav Links */}
      <nav className="flex-1 py-3 flex flex-col gap-1 px-2 overflow-y-auto">
        {/* Dashboard Item */}
        <Link
          href="/app/repositories"
          className={`flex items-center gap-3 px-3 py-2 rounded-xl transition-colors text-sm font-medium ${
            isDashboardActive
              ? "bg-amber/10 text-amber font-semibold"
              : "text-zinc-400 hover:text-white hover:bg-white/5"
          }`}
          title={isCollapsed ? "Dashboard" : undefined}
        >
          <LayoutDashboard className="w-4 h-4 shrink-0" />
          {!isCollapsed && <span className="truncate">Dashboard</span>}
        </Link>

        {/* Chat Item & New Chat */}
        <div className="mt-1">
          <div className="flex items-center justify-between">
            <Link
              href="/app/chat"
              className={`flex-1 flex items-center gap-3 px-3 py-2 rounded-xl transition-colors text-sm font-medium ${
                isChatActive
                  ? "bg-amber/10 text-amber font-semibold"
                  : "text-zinc-400 hover:text-white hover:bg-white/5"
              }`}
              title={isCollapsed ? "Chat" : undefined}
            >
              <MessageSquare className="w-4 h-4 shrink-0" />
              {!isCollapsed && <span className="truncate">Chat</span>}
            </Link>

            {!isCollapsed && (
              <Button
                variant="ghost"
                size="icon"
                onClick={handleNewChat}
                title="New Chat"
                className="h-8 w-8 text-zinc-400 hover:text-amber hover:bg-white/5 ml-1 rounded-lg"
              >
                <Plus className="w-3.5 h-3.5" />
              </Button>
            )}
          </div>

          {/* Sub-category: Chat History / Recents (ChatGPT style) */}
          {!isCollapsed && (
            <div className="mt-3 pl-3 pr-1 space-y-1">
              <div
                onClick={() => setIsRecentsOpen(!isRecentsOpen)}
                className="flex items-center justify-between px-2 py-1 text-[11px] font-medium text-zinc-500 hover:text-zinc-300 cursor-pointer select-none group"
              >
                <span className="flex items-center gap-1.5 uppercase tracking-wider text-[10px]">
                  <Clock className="w-3 h-3" />
                  Recents
                </span>
                <div className="flex items-center gap-1">
                  {chatHistory.length > 0 && (
                    <button
                      onClick={handleClearHistory}
                      title="Clear History"
                      className="opacity-0 group-hover:opacity-100 p-0.5 hover:text-red-400 transition-opacity"
                    >
                      <Trash2 className="w-3 h-3" />
                    </button>
                  )}
                  <ChevronDown
                    className={`w-3 h-3 transition-transform ${isRecentsOpen ? "" : "-rotate-90"}`}
                  />
                </div>
              </div>

              {isRecentsOpen && (
                <div className="space-y-0.5 max-h-56 overflow-y-auto pr-1">
                  {chatHistory.length === 0 ? (
                    <p className="px-2 py-2 text-[11px] text-zinc-600 italic">No recent chats</p>
                  ) : (
                    chatHistory.map((item) => (
                      <button
                        key={item.id}
                        onClick={() => handleSelectHistoryItem(item)}
                        className="w-full text-left px-2.5 py-1.5 rounded-lg text-xs text-zinc-400 hover:text-white hover:bg-white/5 transition-colors truncate block group"
                        title={item.query}
                      >
                        <span className="truncate block font-normal group-hover:text-amber transition-colors">
                          {item.query}
                        </span>
                      </button>
                    ))
                  )}
                </div>
              )}
            </div>
          )}
        </div>
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
