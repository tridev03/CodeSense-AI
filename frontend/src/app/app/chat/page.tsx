"use client";

import { useState, useRef, useCallback, useEffect } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Bot,
  User,
  Send,
  Paperclip,
  Plus,
  X,
  Loader2,
  Copy,
  Check,
  RotateCcw,
  FileCode,
  FolderGit2,
  ChevronDown,
  BookOpen,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { BASE_URL, reposApi, RepositoryResponse } from "@/lib/api";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
}

interface AttachedFile {
  name: string;
  content: string;
  size: number;
}

interface ChatHistoryItem {
  id: string;
  query: string;
  preview: string;
  timestamp: string;
  messages: Message[];
}

export default function DirectChatPage() {
  const router = useRouter();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([]);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Repositories state for the dropdown selector
  const [repos, setRepos] = useState<RepositoryResponse[]>([]);
  const [selectedRepoId, setSelectedRepoId] = useState<string>("none");

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Load active session from sidebar clicks or listen for new chat events
  useEffect(() => {
    reposApi
      .list(0, 100)
      .then((res) => {
        setRepos(res.items);
      })
      .catch(() => {});

    const loadActiveSession = () => {
      try {
        const active = localStorage.getItem("active_direct_chat_session");
        if (active) {
          const parsed: ChatHistoryItem = JSON.parse(active);
          setMessages(parsed.messages);
        }
      } catch {
        // ignore
      }
    };

    const handleNewChatEvent = () => {
      setMessages([]);
      setAttachedFiles([]);
      setInput("");
    };

    loadActiveSession();

    window.addEventListener("load_active_chat_session", loadActiveSession);
    window.addEventListener("start_new_chat_session", handleNewChatEvent);

    return () => {
      window.removeEventListener("load_active_chat_session", loadActiveSession);
      window.removeEventListener("start_new_chat_session", handleNewChatEvent);
    };
  }, []);

  // Save history session and notify sidebar
  const saveSessionToHistory = (newMessages: Message[]) => {
    if (newMessages.length === 0) return;
    const firstUserMsg = newMessages.find((m) => m.role === "user");
    if (!firstUserMsg) return;

    const firstAssistantMsg = newMessages.find((m) => m.role === "assistant");

    try {
      const saved = localStorage.getItem("direct_chat_history_sessions");
      const prev: ChatHistoryItem[] = saved ? JSON.parse(saved) : [];

      const sessionItem: ChatHistoryItem = {
        id: newMessages[0].id,
        query: firstUserMsg.content,
        preview: firstAssistantMsg?.content?.slice(0, 80) || "Conversation...",
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        messages: newMessages,
      };

      const existingIdx = prev.findIndex((item) => item.id === sessionItem.id);
      let updated: ChatHistoryItem[];
      if (existingIdx >= 0) {
        updated = [...prev];
        updated[existingIdx] = sessionItem;
      } else {
        updated = [sessionItem, ...prev].slice(0, 20);
      }

      localStorage.setItem("direct_chat_history_sessions", JSON.stringify(updated));
      localStorage.setItem("active_direct_chat_session", JSON.stringify(sessionItem));
      window.dispatchEvent(new Event("chat_history_updated"));
    } catch {
      // ignore
    }
  };

  const handleRepoSelect = (repoId: string) => {
    if (repoId === "none") {
      setSelectedRepoId("none");
      return;
    }
    router.push(`/app/chat/${repoId}`);
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  const handleFileAttach = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(e.target.files ?? []);
      if (!files.length) return;
      files.forEach((file) => {
        const reader = new FileReader();
        reader.onload = (ev) => {
          const content = ev.target?.result as string;
          setAttachedFiles((prev) => [...prev, { name: file.name, content, size: file.size }]);
        };
        reader.readAsText(file);
      });
      if (fileInputRef.current) fileInputRef.current.value = "";
    },
    []
  );

  const handleSend = async () => {
    const query = input.trim();
    if (!query || isLoading) return;

    const userMsg: Message = { id: Date.now().toString(), role: "user", content: query };
    const nextMessages = [...messages, userMsg];
    setMessages(nextMessages);
    setInput("");
    setIsLoading(true);

    const filesToSend = attachedFiles.map((f) => ({ name: f.name, content: f.content }));
    setAttachedFiles([]);

    try {
      const token =
        typeof window !== "undefined" ? localStorage.getItem("access_token") : null;

      const response = await fetch(`${BASE_URL}/chat/direct/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ query, files: filesToSend }),
      });

      if (!response.ok || !response.body) {
        throw new Error(`HTTP ${response.status}`);
      }

      const assistantId = (Date.now() + 1).toString();
      let currentMessages = [...nextMessages, { id: assistantId, role: "assistant" as const, content: "" }];
      setMessages(currentMessages);
      setIsStreaming(true);

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let streamedContent = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const raw = decoder.decode(value, { stream: true });
        const lines = raw.split("\n");

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const dataStr = line.replace("data: ", "").trim();
            if (dataStr === "[DONE]") continue;
            try {
              const parsed = JSON.parse(dataStr);
              const incomingToken = parsed.token ?? parsed.content ?? "";
              if (incomingToken) {
                streamedContent += incomingToken;
                currentMessages = currentMessages.map((m) =>
                  m.id === assistantId ? { ...m, content: streamedContent } : m
                );
                setMessages(currentMessages);
                scrollToBottom();
              }
              if (parsed.error) {
                toast.error(parsed.error);
              }
            } catch {
              // Ignore parse errors on malformed chunks
            }
          }
        }
      }

      // Save to chat history when stream ends
      saveSessionToHistory(currentMessages);
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : "Network error occurred";
      toast.error(`Error: ${errorMsg}`);
      const errMessages = [
        ...nextMessages,
        {
          id: Date.now().toString(),
          role: "assistant" as const,
          content: `⚠️ Failed to get a response: ${errorMsg}`,
        },
      ];
      setMessages(errMessages);
      saveSessionToHistory(errMessages);
    } finally {
      setIsLoading(false);
      setIsStreaming(false);
      scrollToBottom();
    }
  };

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    toast.success("Copied!");
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleClear = () => {
    if (messages.length === 0) return;
    if (confirm("Start a new chat session?")) {
      localStorage.removeItem("active_direct_chat_session");
      setMessages([]);
      setAttachedFiles([]);
      window.dispatchEvent(new Event("start_new_chat_session"));
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-5rem)] max-w-7xl mx-auto pb-4 overflow-hidden">
      {/* Top Header */}
      <div className="flex items-center justify-between py-2 border-b border-[#242424] px-2 mb-3 shrink-0">
        <div className="flex items-center gap-3">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-light text-[#F5F5F5]">Chat</h2>
              <Badge className="bg-[#1a1000] text-[#D99A45] border border-[#D99A45]/30 text-[10px] px-2">
                File / Direct Chat
              </Badge>
            </div>
            <p className="text-[11px] text-[#71717A]">
              Upload local code files or select a repository from the selector
            </p>
          </div>
        </div>

        {/* Controls */}
        <div className="flex items-center gap-3">
          {/* Repository Selector Dropdown */}
          <div className="relative">
            <FolderGit2 className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[#D99A45] pointer-events-none" />
            <select
              value={selectedRepoId}
              onChange={(e) => handleRepoSelect(e.target.value)}
              className="appearance-none pl-8 pr-7 py-1.5 bg-[#141414] hover:bg-[#1A1A1A] border border-[#2D2D2D] hover:border-[#D99A45]/50 rounded-xl text-xs text-[#F5F5F5] font-medium transition-colors cursor-pointer outline-none focus:border-[#D99A45]"
            >
              <option value="none">📁 No repository (Direct / File Chat)</option>
              {repos.map((repo) => (
                <option key={repo.id} value={repo.id}>
                  📦 {repo.name} {repo.status === "indexed" ? "✓" : `(${repo.status})`}
                </option>
              ))}
            </select>
            <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[#71717A] pointer-events-none" />
          </div>

          <Button
            variant="ghost"
            size="sm"
            onClick={handleClear}
            title="Start New Chat"
            className="text-[#71717A] hover:text-[#D99A45] text-xs h-8 px-2.5 flex items-center gap-1.5"
          >
            <Plus className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">New Chat</span>
          </Button>
        </div>
      </div>

      {/* Main Split Layout */}
      <div className="flex-1 flex gap-4 min-h-0">
        {/* Messages and Input column */}
        <div className="flex-1 flex flex-col min-h-0 bg-[#0D0D0D] border border-[#242424] rounded-2xl overflow-hidden">
          {/* Messages scroll area */}
          <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-6">
            {messages.length === 0 ? (
              <div className="h-full flex flex-col justify-center items-center text-center p-6 max-w-md mx-auto">
                <div className="w-12 h-12 rounded-2xl bg-[#141414] border border-[#303030] flex items-center justify-center text-[#D99A45] mb-4">
                  <Bot className="w-6 h-6" />
                </div>
                <h3 className="text-lg font-light text-[#F5F5F5]">Chat without a repository</h3>
                <p className="text-xs text-[#71717A] mt-1 mb-6">
                  Click the <span className="text-[#D99A45] font-bold">+</span> button below to attach local code files, or select a repository from the top dropdown.
                </p>
                <div className="w-full space-y-2">
                  {[
                    "Summarize the main purpose of this file",
                    "What functions or classes are defined here?",
                    "Are there any bugs or improvements you can spot?",
                    "Explain how this code works step by step",
                  ].map((s) => (
                    <button
                      key={s}
                      onClick={() => setInput(s)}
                      className="w-full text-left text-xs text-[#A1A1AA] hover:text-[#F5F5F5] bg-[#141414] hover:bg-[#1A1A1A] border border-[#242424] hover:border-[#D99A45]/40 rounded-xl p-3 transition-colors"
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((m) => (
                <div
                  key={m.id}
                  className={`flex gap-3 ${m.role === "user" ? "justify-end" : "justify-start"}`}
                >
                  {m.role === "assistant" && (
                    <div className="w-8 h-8 rounded-xl bg-[#141414] border border-[#242424] flex items-center justify-center text-[#D99A45] shrink-0 mt-1">
                      <Bot className="w-4 h-4" />
                    </div>
                  )}

                  <div className="max-w-[85%] space-y-2">
                    <div
                      className={`p-4 rounded-2xl text-xs sm:text-sm leading-relaxed ${
                        m.role === "user"
                          ? "bg-[#1A1408] border border-[#D99A45]/30 text-[#F5F5F5]"
                          : "bg-[#141414] border border-[#242424] text-[#E4E4E7]"
                      }`}
                    >
                      <div className="prose prose-invert prose-xs sm:prose-sm max-w-none prose-pre:bg-[#0A0A0A] prose-pre:border prose-pre:border-[#242424] prose-code:text-[#D99A45]">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                        {isStreaming && m.role === "assistant" && m === messages[messages.length - 1] && (
                          <span className="inline-block w-[2px] h-[1em] bg-[#D99A45] ml-0.5 align-middle animate-pulse" />
                        )}
                      </div>
                    </div>

                    {m.role === "assistant" && (
                      <div className="flex items-center gap-2 pl-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-6 w-6 text-[#71717A] hover:text-[#F5F5F5]"
                          onClick={() => handleCopy(m.content, m.id)}
                          title="Copy text"
                        >
                          {copiedId === m.id ? (
                            <Check className="w-3 h-3 text-[#10B981]" />
                          ) : (
                            <Copy className="w-3 h-3" />
                          )}
                        </Button>
                      </div>
                    )}
                  </div>

                  {m.role === "user" && (
                    <div className="w-8 h-8 rounded-xl bg-[#242424] flex items-center justify-center text-[#F5F5F5] shrink-0 mt-1">
                      <User className="w-4 h-4" />
                    </div>
                  )}
                </div>
              ))
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Composer */}
          <div className="p-3 bg-[#080808] border-t border-[#242424]">
            {/* Attached file badges preview */}
            {attachedFiles.length > 0 && (
              <div className="flex flex-wrap gap-1.5 pb-2.5 mb-1 border-b border-[#1E1E1E]">
                {attachedFiles.map((file, idx) => (
                  <div
                    key={`${file.name}-${idx}`}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[#141414] border border-[#2D2D2D] text-[#D99A45] text-[11px] font-mono group"
                  >
                    <Paperclip className="w-3 h-3 text-[#D99A45] shrink-0" />
                    <span className="truncate max-w-[160px]">{file.name}</span>
                    <span className="text-[10px] text-[#71717A]">
                      ({(file.size / 1024).toFixed(1)} KB)
                    </span>
                    <button
                      type="button"
                      onClick={() => setAttachedFiles((prev) => prev.filter((_, i) => i !== idx))}
                      className="text-[#71717A] hover:text-[#EF4444] transition-colors"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            <form
              onSubmit={(e) => { e.preventDefault(); handleSend(); }}
              className="flex items-end gap-2"
            >
              {/* Hidden file input */}
              <input
                type="file"
                ref={fileInputRef}
                onChange={handleFileAttach}
                multiple
                accept=".py,.ts,.tsx,.js,.jsx,.json,.yaml,.yml,.toml,.md,.txt,.html,.css,.sql,.sh,.env,.java,.go,.rs,.cpp,.c,.rb"
                className="hidden"
              />

              {/* + file button */}
              <Button
                type="button"
                variant="outline"
                onClick={() => fileInputRef.current?.click()}
                disabled={isLoading}
                title="Add local files to prompt"
                className="h-11 w-11 rounded-xl shrink-0 p-0 bg-[#141414] border-[#242424] hover:bg-[#1C1C1C] hover:border-[#D99A45]/50 text-[#A1A1AA] hover:text-[#D99A45] transition-colors"
              >
                <Plus className="w-5 h-5" />
              </Button>

              <Textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSend();
                  }
                }}
                placeholder="Ask about functions, logic, architecture, or attach files..."
                className="min-h-[44px] max-h-32 bg-[#141414] border-[#242424] text-[#F5F5F5] placeholder:text-[#52525B] focus:border-[#D99A45] focus:ring-[#D99A45]/20 rounded-xl resize-none py-2.5 px-3 text-xs sm:text-sm"
              />

              <Button
                type="submit"
                disabled={isLoading || (!input.trim() && attachedFiles.length === 0)}
                className="bg-[#D99A45] hover:bg-[#D99A45]/90 text-black h-11 w-11 rounded-xl shrink-0 p-0"
              >
                {isLoading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Send className="w-4 h-4" />
                )}
              </Button>
            </form>
          </div>
        </div>

        {/* Right Panel: Source Citations (Standardized across all views) */}
        <div className="hidden lg:flex w-80 flex-col bg-[#0D0D0D] border border-[#242424] rounded-2xl overflow-hidden">
          <div className="p-3.5 border-b border-[#242424] flex items-center justify-between">
            <span className="text-xs font-medium text-[#F5F5F5] flex items-center gap-1.5">
              <BookOpen className="w-3.5 h-3.5 text-[#D99A45]" />
              Source Citations
            </span>
          </div>

          <div className="flex-1 p-6 flex flex-col items-center justify-center text-center text-[#52525B]">
            <div className="text-3xl mb-3 font-mono">&lt;/&gt;</div>
            <p className="text-xs font-medium text-[#71717A]">No citation selected.</p>
            <p className="text-[11px] text-[#52525B] mt-1 max-w-[200px]">
              Select a repository from the top to ground answers with source citations.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
