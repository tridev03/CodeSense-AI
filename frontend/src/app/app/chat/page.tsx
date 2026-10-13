"use client";

import { useState, useRef, useCallback } from "react";
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
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { BASE_URL } from "@/lib/api";

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

export default function DirectChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [attachedFiles, setAttachedFiles] = useState<AttachedFile[]>([]);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

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
    setMessages((prev) => [...prev, userMsg]);
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
      setMessages((prev) => [...prev, { id: assistantId, role: "assistant", content: "" }]);
      setIsStreaming(true);

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

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
          let chunk: { token?: string; done?: boolean; error?: string };
          try { chunk = JSON.parse(jsonStr); } catch { continue; }

          if (chunk.error) {
            toast.error(chunk.error);
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? { ...m, content: `⚠️ **Error**: ${chunk.error}` }
                  : m
              )
            );
            break;
          }
          if (chunk.token !== undefined && chunk.token !== null) {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId ? { ...m, content: m.content + chunk.token } : m
              )
            );
          }
        }
        scrollToBottom();
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to get response";
      toast.error(msg);
      setMessages((prev) => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          role: "assistant",
          content: `⚠️ **Error**: ${msg}`,
        },
      ]);
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
    if (confirm("Clear conversation?")) {
      setMessages([]);
      setAttachedFiles([]);
    }
  };

  return (
    <div className="flex flex-col h-[calc(100vh-5rem)] max-w-4xl mx-auto pb-4 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between py-2 border-b border-[#242424] px-2 mb-3 shrink-0">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-base font-light text-[#F5F5F5]">File Chat</h2>
            <Badge className="bg-[#1a1000] text-[#D99A45] border border-[#D99A45]/30 text-[10px] px-2">
              No repo needed
            </Badge>
          </div>
          <p className="text-[11px] text-[#71717A]">
            Upload files with <span className="text-[#D99A45]">+</span> and ask questions about them
          </p>
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

      {/* Messages */}
      <div className="flex-1 flex flex-col min-h-0 bg-[#0D0D0D] border border-[#242424] rounded-2xl overflow-hidden">
        <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-6">
          {messages.length === 0 ? (
            <div className="h-full flex flex-col justify-center items-center text-center p-6 max-w-md mx-auto">
              <div className="w-12 h-12 rounded-2xl bg-[#141414] border border-[#303030] flex items-center justify-center text-[#D99A45] mb-4">
                <Bot className="w-6 h-6" />
              </div>
              <h3 className="text-lg font-light text-[#F5F5F5]">Chat without a repository</h3>
              <p className="text-xs text-[#71717A] mt-1 mb-6">
                Click the <span className="text-[#D99A45] font-bold">+</span> button to attach local files, then ask questions about them.
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
                    {m.role === "assistant" && (
                      <div className="flex items-center justify-end pt-3 mt-3 border-t border-[#242424]">
                        <button
                          onClick={() => handleCopy(m.content, m.id)}
                          className="text-[10px] text-[#71717A] hover:text-[#D99A45] flex items-center gap-1 transition-colors"
                        >
                          {copiedId === m.id ? (
                            <Check className="w-3 h-3 text-[#22C55E]" />
                          ) : (
                            <Copy className="w-3 h-3" />
                          )}
                          Copy
                        </button>
                      </div>
                    )}
                  </div>
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
                <span className="text-xs text-[#A1A1AA]">Thinking...</span>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Composer */}
        <div className="p-3 bg-[#080808] border-t border-[#242424]">
          {/* Attached file chips */}
          {attachedFiles.length > 0 && (
            <div className="flex flex-wrap gap-1.5 pb-2.5 mb-1 border-b border-[#1E1E1E]">
              {attachedFiles.map((file, idx) => (
                <div
                  key={`${file.name}-${idx}`}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[#141414] border border-[#2D2D2D] text-[#D99A45] text-[11px] font-mono"
                >
                  <FileCode className="w-3 h-3 shrink-0" />
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
              title="Attach local files"
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
              placeholder="Ask anything about your files…"
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
    </div>
  );
}

