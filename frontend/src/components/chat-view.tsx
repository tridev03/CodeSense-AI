"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  chatApi,
  agentApi,
  reposApi,
  RepositoryResponse,
  Citation,
  ChatRequest,
  AgentQueryRequest,
  BASE_URL,
} from "@/lib/api";
import { toast } from "sonner";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  ArrowLeft,
  Send,
  Bot,
  User,
  Sparkles,
  FileCode,
  Copy,
  Check,
  RotateCcw,
  ChevronRight,
  ChevronDown,
  Loader2,
  FolderGit2,
  BookOpen,
  Code2,
  Maximize2,
  Paperclip,
  Plus,
  X,
} from "lucide-react";
import { CitationInspector } from "@/components/citation-inspector";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  model?: string;
  tokensUsed?: number;
  isAgent?: boolean;
}

export interface AttachedFile {
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

interface ChatViewProps {
  initialRepoId?: string;
  showRepoSelector?: boolean;
}

const PROMPT_SUGGESTIONS = [
  "Explain the overall architecture and folder structure",
  "How does user authentication work in this codebase?",
  "What database models and relations are defined?",
  "Show the main API routes and request flows",
];

export function ChatView({ initialRepoId, showRepoSelector = true }: ChatViewProps) {
  const router = useRouter();
  const currentRepoId = initialRepoId || "none";
  const isDirectChat = currentRepoId === "none";

  const [repo, setRepo] = useState<RepositoryResponse | null>(null);
  const [allRepos, setAllRepos] = useState<RepositoryResponse[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [agentMode, setAgentMode] = useState(false);
  const [selectedCitation, setSelectedCitation] = useState<Citation | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [isInspectorOpen, setIsInspectorOpen] = useState(false);
  const [reconnectAttempt, setReconnectAttempt] = useState<number>(0);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([]);

  // ── Load Repository List & Active Repo Details ──────────────────────────────
  useEffect(() => {
    reposApi
      .list(0, 100)
      .then((res) => setAllRepos(res.items))
      .catch(() => {});

    if (!isDirectChat && initialRepoId) {
      reposApi.get(initialRepoId).then(setRepo).catch(() => {});
    }
  }, [initialRepoId, isDirectChat]);

  // ── Load Chat History ───────────────────────────────────────────────────────
  useEffect(() => {
    if (!isDirectChat && initialRepoId) {
      const saved = localStorage.getItem(`chat_history_${initialRepoId}`);
      if (saved) {
        try {
          setMessages(JSON.parse(saved));
        } catch {
          // ignore
        }
      }
    } else {
      // Direct chat: load active session
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
    }
  }, [initialRepoId, isDirectChat]);

  // ── Auto-save Messages ──────────────────────────────────────────────────────
  useEffect(() => {
    if (messages.length === 0) return;

    if (!isDirectChat && initialRepoId) {
      localStorage.setItem(`chat_history_${initialRepoId}`, JSON.stringify(messages));
    } else {
      // Direct chat session saving + broadcast for sidebar history
      const firstUserMsg = messages.find((m) => m.role === "user");
      if (!firstUserMsg) return;

      const firstAssistantMsg = messages.find((m) => m.role === "assistant");
      try {
        const saved = localStorage.getItem("direct_chat_history_sessions");
        const prev: ChatHistoryItem[] = saved ? JSON.parse(saved) : [];

        const sessionItem: ChatHistoryItem = {
          id: messages[0].id,
          query: firstUserMsg.content,
          preview: firstAssistantMsg?.content?.slice(0, 80) || "Conversation...",
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
          messages,
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
    }
  }, [messages, initialRepoId, isDirectChat]);

  // ── Scroll to Bottom ────────────────────────────────────────────────────────
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  // ── File Attachment Handler ─────────────────────────────────────────────────
  const handleFileAttach = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    if (!files.length) return;

    files.forEach((file) => {
      const reader = new FileReader();
      reader.onload = (ev) => {
        const content = ev.target?.result as string;
        setAttachedFiles((prev) => [
          ...prev,
          { name: file.name, content, size: file.size },
        ]);
      };
      reader.readAsText(file);
    });

    if (fileInputRef.current) fileInputRef.current.value = "";
  }, []);

  // ── Dropdown Switcher ───────────────────────────────────────────────────────
  const handleRepoChange = (targetId: string) => {
    if (targetId === "none") {
      router.push("/app/chat");
    } else {
      router.push(`/app/chat/${targetId}`);
    }
  };

  // ── Send Message ────────────────────────────────────────────────────────────
  const handleSend = async (queryToSend?: string) => {
    const rawQuery = (queryToSend ?? input).trim();
    if (!rawQuery || isLoading) return;

    // Check repository requirement if not in direct chat
    const targetRepoId = !isDirectChat ? initialRepoId : allRepos.length > 0 ? allRepos[0].id : null;

    if (!targetRepoId && !attachedFiles.length) {
      toast.error("Please select a repository or attach a file to analyze.");
      setMessages((prev) => [
        ...prev,
        { id: Date.now().toString(), role: "user", content: rawQuery },
        {
          id: (Date.now() + 1).toString(),
          role: "assistant",
          content: "⚠️ **No repository connected yet.**\n\nTo chat with your codebase, please select a repository from the dropdown above or attach files with the **+** button.",
        },
      ]);
      setInput("");
      return;
    }

    const effectiveRepoId = targetRepoId || allRepos[0]?.id;

    // Build enriched query with attached files
    let finalQuery = rawQuery;
    if (attachedFiles.length > 0) {
      const fileContext = attachedFiles
        .map((f) => `[File: ${f.name}]\n\`\`\`\n${f.content}\n\`\`\``)
        .join("\n\n");
      finalQuery = `${fileContext}\n\nUser question: ${rawQuery}`;
    }

    const userMsg: Message = {
      id: Date.now().toString(),
      role: "user",
      content: rawQuery,
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setAttachedFiles([]);
    setIsLoading(true);

    try {
      if (agentMode && effectiveRepoId) {
        // Agent reasoning mode
        const payload: AgentQueryRequest = {
          query: finalQuery,
          top_k: 5,
          max_reflections: 2,
          include_citations: true,
        };
        const res = await agentApi.query(effectiveRepoId, payload);
        const assistantMsg: Message = {
          id: (Date.now() + 1).toString(),
          role: "assistant",
          content: res.answer,
          citations: res.citations,
          model: res.model,
          tokensUsed: res.tokens_used,
          isAgent: true,
        };
        setMessages((prev) => [...prev, assistantMsg]);
        if (res.citations.length > 0) setSelectedCitation(res.citations[0]);
      } else if (effectiveRepoId) {
        // Chat mode with SSE streaming & exponential backoff reconnection
        const payload: ChatRequest = {
          query: finalQuery,
          top_k: 10,
          include_citations: true,
          retrieval_mode: "hybrid",
          use_reranker: true,
        };

        const token = typeof window !== "undefined" ? localStorage.getItem("access_token") : null;
        const assistantId = (Date.now() + 1).toString();
        const MAX_RETRIES = 3;
        const RETRY_DELAYS = [500, 1000, 2000];

        setMessages((prev) => [...prev, { id: assistantId, role: "assistant", content: "" }]);
        setIsStreaming(true);

        let streamSucceeded = false;

        for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
          if (attempt > 0) {
            setReconnectAttempt(attempt);
            await new Promise((resolve) => setTimeout(resolve, RETRY_DELAYS[attempt - 1]));
          }

          try {
            const response = await fetch(`${BASE_URL}/repositories/${effectiveRepoId}/chat/stream`, {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                ...(token ? { Authorization: `Bearer ${token}` } : {}),
              },
              body: JSON.stringify(payload),
            });

            if (!response.ok || !response.body) throw new Error(`HTTP ${response.status}`);

            setReconnectAttempt(0);

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = "";
            let finalCitations: Citation[] = [];

             
            while (true) {
              const { done, value } = await reader.read();
              if (done) break;

              buffer += decoder.decode(value, { stream: true });
              const lines = buffer.split("\n");
              buffer = lines.pop() ?? "";

              for (const line of lines) {
                if (!line.startsWith("data:")) continue;
                const jsonStr = line.slice(5).trim();
                if (!jsonStr) continue;

                let chunk: { token?: string; citations?: Citation[]; done?: boolean; error?: string };
                try {
                  chunk = JSON.parse(jsonStr);
                } catch {
                  continue;
                }

                if (chunk.error) {
                  throw new Error(chunk.error);
                }

                if (chunk.token !== undefined && chunk.token !== null) {
                  setMessages((prev) =>
                    prev.map((m) => (m.id === assistantId ? { ...m, content: m.content + chunk.token } : m))
                  );
                }

                if (chunk.done) {
                  finalCitations = chunk.citations ?? [];
                  setMessages((prev) =>
                    prev.map((m) => (m.id === assistantId ? { ...m, citations: finalCitations } : m))
                  );
                  if (finalCitations.length > 0) setSelectedCitation(finalCitations[0]);
                }
              }
            }

            streamSucceeded = true;
            break; // Stream succeeded, break retry loop!
          } catch (streamErr) {
            console.warn(`SSE stream attempt ${attempt + 1}/${MAX_RETRIES + 1} failed:`, streamErr);
            if (attempt === MAX_RETRIES) {
              break;
            }
          }
        }

        setIsStreaming(false);
        setReconnectAttempt(0);

        if (!streamSucceeded) {
          // Graceful fallback to non-streaming /chat endpoint
          const res = await chatApi.send(effectiveRepoId, payload);
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId
                ? {
                    ...m,
                    content: res.answer,
                    citations: res.citations,
                    model: res.model,
                    tokensUsed: res.tokens_used,
                  }
                : m
            )
          );
          if (res.citations.length > 0) setSelectedCitation(res.citations[0]);
        }
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to generate answer";
      toast.error(msg);
      setMessages((prev) => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          role: "assistant",
          content: `⚠️ **Error processing query**: ${msg}\n\nPlease check your backend connection or indexing status.`,
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleCopy = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    toast.success("Copied to clipboard");
    setTimeout(() => setCopiedId(null), 2000);
  };

  const handleClear = () => {
    if (confirm("Clear conversation history?")) {
      setMessages([]);
      if (!isDirectChat && initialRepoId) {
        localStorage.removeItem(`chat_history_${initialRepoId}`);
      } else {
        localStorage.removeItem("active_direct_chat_session");
      }
      setSelectedCitation(null);
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-5rem)] max-w-7xl mx-auto pb-4 overflow-hidden">
      {/* Top Header */}
      <div className="flex items-center justify-between py-2 border-b border-[#242424] px-2 mb-3 shrink-0">
        <div className="flex items-center gap-3">
          {!isDirectChat && (
            <Link
              href={`/app/repositories/${initialRepoId}`}
              className="text-[#71717A] hover:text-[#D99A45] transition-colors p-1"
            >
              <ArrowLeft className="w-4 h-4" />
            </Link>
          )}
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-light text-[#F5F5F5]">
                {repo?.name || (isDirectChat ? "Direct & File Chat" : "Codebase")}
              </h2>
              <Badge className="bg-[#1a1000] text-[#D99A45] border border-[#D99A45]/30 text-[10px] px-2">
                Chat
              </Badge>
            </div>
            <p className="text-[11px] text-[#71717A]">
              Grounded on Qdrant embeddings · {messages.length} messages
            </p>
          </div>
        </div>

        {/* Controls */}
        <div className="flex items-center gap-3">
          {showRepoSelector && (
            <div className="relative">
              <FolderGit2 className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[#D99A45] pointer-events-none" />
              <select
                value={currentRepoId}
                onChange={(e) => handleRepoChange(e.target.value)}
                className="appearance-none pl-8 pr-7 py-1.5 bg-[#141414] hover:bg-[#1A1A1A] border border-[#2D2D2D] hover:border-[#D99A45]/50 rounded-xl text-xs text-[#F5F5F5] font-medium transition-colors cursor-pointer outline-none focus:border-[#D99A45]"
              >
                <option value="none">📁 Switch to Direct / File Chat</option>
                {allRepos.map((r) => (
                  <option key={r.id} value={r.id}>
                    📦 {r.name} {r.status === "indexed" ? "✓" : `(${r.status})`}
                  </option>
                ))}
              </select>
              <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-[#71717A] pointer-events-none" />
            </div>
          )}

          <div className="flex items-center gap-2">
            <Switch
              id="agent-mode"
              checked={agentMode}
              onCheckedChange={setAgentMode}
              className="data-[state=checked]:bg-[#D99A45]"
            />
            <Label
              htmlFor="agent-mode"
              className="text-xs text-[#A1A1AA] cursor-pointer flex items-center gap-1"
            >
              <Sparkles className="w-3.5 h-3.5 text-[#D99A45]" />
              Agent Mode
            </Label>
          </div>

          <Button
            variant="ghost"
            size="sm"
            onClick={handleClear}
            title="Clear Chat"
            className="text-[#71717A] hover:text-[#EF4444] text-xs h-8 px-2"
          >
            <RotateCcw className="w-3.5 h-3.5" />
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
                <h3 className="text-lg font-light text-[#F5F5F5]">Ask about this codebase</h3>
                <p className="text-xs text-[#71717A] mt-1 mb-6">
                  Get precise, source-grounded answers with file citations and line numbers.
                </p>

                <div className="w-full space-y-2">
                  {PROMPT_SUGGESTIONS.map((suggestion) => (
                    <button
                      key={suggestion}
                      onClick={() => handleSend(suggestion)}
                      className="w-full text-left text-xs text-[#A1A1AA] hover:text-[#F5F5F5] bg-[#141414] hover:bg-[#1A1A1A] border border-[#242424] hover:border-[#D99A45]/40 rounded-xl p-3 transition-colors flex items-center justify-between group"
                    >
                      <span>{suggestion}</span>
                      <ChevronRight className="w-3.5 h-3.5 text-[#52525B] group-hover:text-[#D99A45]" />
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
                      {m.isAgent ? <Sparkles className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
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
                          <span
                            className="inline-block w-[2px] h-[1em] bg-[#D99A45] ml-0.5 align-middle animate-pulse"
                            aria-hidden="true"
                          />
                        )}
                      </div>

                      {reconnectAttempt > 0 && isStreaming && m === messages[messages.length - 1] && (
                        <div className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md bg-amber-500/10 border border-amber-500/30 text-[10px] text-amber-400 mt-2 font-mono">
                          <Loader2 className="w-2.5 h-2.5 animate-spin" />
                          <span>Reconnecting stream (attempt {reconnectAttempt}/3)...</span>
                        </div>
                      )}

                      {m.role === "assistant" && (
                        <div className="flex items-center justify-between pt-3 mt-3 border-t border-[#242424] text-[10px] text-[#71717A]">
                          <span>
                            {m.model || "qwen-27b"} {m.tokensUsed ? `· ${m.tokensUsed} tokens` : ""}
                          </span>
                          <button
                            onClick={() => handleCopy(m.content, m.id)}
                            className="hover:text-[#D99A45] flex items-center gap-1 transition-colors"
                          >
                            {copiedId === m.id ? (
                              <Check className="w-3 h-3 text-[#22C55E]" />
                            ) : (
                              <Copy className="w-3 h-3" />
                            )}
                            <span>Copy</span>
                          </button>
                        </div>
                      )}
                    </div>

                    {m.citations && m.citations.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 pt-1">
                        {m.citations.map((c, i) => (
                          <button
                            key={i}
                            onClick={() => setSelectedCitation(c)}
                            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-[#080808] border border-[#242424] hover:border-[#D99A45]/50 text-[10px] text-[#D99A45] transition-colors"
                          >
                            <FileCode className="w-3 h-3" />
                            <span className="font-mono truncate max-w-[150px]">
                              {c.file_path.split("/").pop()}
                            </span>
                            {c.start_line && <span>:{c.start_line}</span>}
                          </button>
                        ))}
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

            {isLoading && !isStreaming && (
              <div className="flex gap-3">
                <div className="w-8 h-8 rounded-xl bg-[#141414] border border-[#242424] flex items-center justify-center text-[#D99A45] shrink-0">
                  <Bot className="w-4 h-4" />
                </div>
                <div className="bg-[#141414] border border-[#242424] rounded-2xl p-4 flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-[#D99A45] animate-ping" />
                  <span className="text-xs text-[#A1A1AA]">
                    {agentMode ? "Agent reasoning and calling tools..." : "Searching code vectors..."}
                  </span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Composer */}
          <div className="p-3 bg-[#080808] border-t border-[#242424]">
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
                      className="text-[#71717A] hover:text-[#EF4444] transition-colors p-0.5 rounded"
                      title="Remove file"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                ))}
              </div>
            )}

            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleSend();
              }}
              className="flex items-end gap-2"
            >
              <input
                type="file"
                ref={fileInputRef}
                onChange={handleFileAttach}
                multiple
                accept=".py,.ts,.tsx,.js,.jsx,.json,.yaml,.yml,.toml,.md,.txt,.html,.css,.sql,.sh,.env"
                className="hidden"
              />

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
                placeholder={
                  agentMode
                    ? "Ask a complex multi-step question for the agent..."
                    : "Ask about functions, logic, architecture..."
                }
                className="min-h-[44px] max-h-32 bg-[#141414] border-[#242424] text-[#F5F5F5] placeholder:text-[#52525B] focus:border-[#D99A45] focus:ring-[#D99A45]/20 rounded-xl resize-none py-2.5 px-3 text-xs sm:text-sm"
              />
              <Button
                type="submit"
                disabled={isLoading || (!input.trim() && attachedFiles.length === 0)}
                className="bg-[#D99A45] hover:bg-[#D99A45]/90 text-black h-11 w-11 rounded-xl shrink-0 p-0"
              >
                {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
              </Button>
            </form>
          </div>
        </div>

        {/* Right Citations & Evidence Panel */}
        <div className="hidden lg:flex w-80 flex-col bg-[#0D0D0D] border border-[#242424] rounded-2xl overflow-hidden">
          <div className="p-3.5 border-b border-[#242424] flex items-center justify-between">
            <span className="text-xs font-medium text-[#F5F5F5] flex items-center gap-1.5">
              <BookOpen className="w-3.5 h-3.5 text-[#D99A45]" />
              Source Citations
            </span>
            {selectedCitation && (
              <Badge className="bg-[#141414] text-[#A1A1AA] border-[#303030] text-[10px]">Active</Badge>
            )}
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {selectedCitation ? (
              <div className="space-y-3">
                <div className="p-3 bg-[#141414] border border-[#242424] rounded-xl space-y-1.5">
                  <div className="flex items-center gap-1.5 text-xs text-[#D99A45] font-mono break-all">
                    <FileCode className="w-3.5 h-3.5 shrink-0" />
                    <span>{selectedCitation.file_path}</span>
                  </div>
                  {selectedCitation.start_line && (
                    <p className="text-[11px] text-[#71717A]">
                      Lines {selectedCitation.start_line}
                      {selectedCitation.end_line ? ` - ${selectedCitation.end_line}` : ""}
                    </p>
                  )}
                  {selectedCitation.symbol && (
                    <p className="text-[11px] text-[#A1A1AA]">
                      Symbol: <span className="font-mono text-[#F5F5F5]">{selectedCitation.symbol}</span>
                    </p>
                  )}
                </div>

                {selectedCitation.snippet && (
                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <span className="text-[11px] text-[#71717A] block">Evidence Snippet</span>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setIsInspectorOpen(true)}
                        className="text-[11px] text-[#D99A45] hover:text-[#F5F5F5] hover:bg-[#141414] h-6 px-2 gap-1"
                      >
                        <Maximize2 className="w-3 h-3" />
                        Inspect Code
                      </Button>
                    </div>
                    <pre
                      onClick={() => setIsInspectorOpen(true)}
                      title="Click to open code inspector"
                      className="p-3 bg-[#080808] border border-[#1A1A1A] hover:border-[#D99A45]/30 cursor-pointer rounded-xl text-[11px] font-mono text-[#D4D4D8] overflow-x-auto whitespace-pre-wrap leading-relaxed max-h-72 transition-colors"
                    >
                      <code>{selectedCitation.snippet}</code>
                    </pre>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-16 text-[#71717A]">
                <Code2 className="w-8 h-8 mx-auto opacity-30 mb-2" />
                <p className="text-xs">No citation selected.</p>
                <p className="text-[11px] mt-1 opacity-70">
                  Ask a question to see source citations here.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Code Citation Inspector Drawer */}
      <CitationInspector
        isOpen={isInspectorOpen}
        onClose={() => setIsInspectorOpen(false)}
        citation={
          selectedCitation
            ? {
                file_path: selectedCitation.file_path,
                content: selectedCitation.snippet || "",
                chunk_id: selectedCitation.chunk_id,
              }
            : null
        }
      />
    </div>
  );
}

