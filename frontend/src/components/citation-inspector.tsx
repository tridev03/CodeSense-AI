"use client";

import { useState, useMemo, useEffect } from "react";
import { Citation } from "@/lib/api";
import { toast } from "sonner";
import {
  X,
  Copy,
  Check,
  FileCode,
  Search,
  Code2,
  ExternalLink,
  Sparkles,
  Layers,
  ChevronRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";

interface CitationInspectorProps {
  isOpen: boolean;
  onClose: () => void;
  citation: Citation | null;
}

export function CitationInspector({ isOpen, onClose, citation }: CitationInspectorProps) {
  const [copied, setCopied] = useState(false);
  const [filterText, setFilterText] = useState("");

  // Handle Escape key to close
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  // Prevent background scroll when open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "unset";
    }
    return () => {
      document.body.style.overflow = "unset";
    };
  }, [isOpen]);

  const contentText = citation?.content || citation?.snippet || "";

  const lines = useMemo(() => {
    if (!contentText) return [];
    return contentText.split("\n");
  }, [contentText]);

  const filteredLines = useMemo(() => {
    if (!filterText.trim()) {
      return lines.map((line: string, idx: number) => ({ line, originalIdx: idx + 1 }));
    }
    const q = filterText.toLowerCase();
    return lines
      .map((line: string, idx: number) => ({ line, originalIdx: idx + 1 }))
      .filter(({ line }: { line: string }) => line.toLowerCase().includes(q));
  }, [lines, filterText]);

  const handleCopy = () => {
    if (!contentText) return;
    navigator.clipboard.writeText(contentText);
    setCopied(true);
    toast.success("Snippet copied to clipboard");
    setTimeout(() => setCopied(false), 2000);
  };

  if (!isOpen || !citation) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* Backdrop */}
      <div
        onClick={onClose}
        className="fixed inset-0 bg-black/80 backdrop-blur-sm transition-opacity animate-in fade-in duration-200"
      />

      {/* Slide-over Drawer Panel */}
      <div className="relative z-10 w-full max-w-2xl h-full bg-[#080808] border-l border-[#242424] shadow-2xl flex flex-col animate-in slide-in-from-right duration-300">
        {/* Drawer Header */}
        <div className="p-4 sm:p-5 border-b border-[#1C1C1C] flex items-center justify-between gap-3 bg-[#0D0D0D]">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-8 h-8 rounded-lg bg-[#141414] border border-[#242424] flex items-center justify-center text-[#D99A45] shrink-0">
              <FileCode className="w-4 h-4" />
            </div>
            <div className="min-w-0">
              <h2 className="text-sm font-semibold text-[#F5F5F5] truncate font-mono">
                {citation.file_path}
              </h2>
              <div className="flex items-center gap-2 mt-0.5">
                {citation.chunk_id && (
                  <span className="text-[11px] text-[#71717A] font-mono">
                    chunk: {citation.chunk_id.slice(0, 8)}
                  </span>
                )}
                {citation.score !== undefined && (
                  <Badge
                    variant="outline"
                    className="bg-[#141414] border-[#242424] text-[#D99A45] text-[10px] px-1.5 py-0"
                  >
                    Match: {Math.round(citation.score * 100)}%
                  </Badge>
                )}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <Button
              variant="outline"
              size="sm"
              onClick={handleCopy}
              className="bg-[#141414] border-[#242424] hover:bg-[#1A1A1A] hover:border-[#D99A45]/40 text-xs text-[#F5F5F5] h-8 px-2.5 gap-1.5"
            >
              {copied ? (
                <>
                  <Check className="w-3.5 h-3.5 text-emerald-400" />
                  Copied
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5 text-[#71717A]" />
                  Copy Snippet
                </>
              )}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={onClose}
              className="text-[#71717A] hover:text-[#F5F5F5] hover:bg-[#141414] h-8 w-8 p-0 rounded-lg"
            >
              <X className="w-4 h-4" />
            </Button>
          </div>
        </div>

        {/* Filter / Search within Snippet */}
        <div className="p-3 bg-[#0A0A0A] border-b border-[#1C1C1C] flex items-center justify-between gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[#71717A]" />
            <Input
              value={filterText}
              onChange={(e) => setFilterText(e.target.value)}
              placeholder="Find inside code snippet..."
              className="pl-8 bg-[#121212] border-[#242424] text-xs h-7 text-[#F5F5F5] placeholder:text-[#71717A] focus-visible:border-[#D99A45]"
            />
          </div>
          <span className="text-[11px] text-[#71717A] font-mono shrink-0">
            {filteredLines.length} / {lines.length} lines
          </span>
        </div>

        {/* Code View with Line Numbers */}
        <div className="flex-1 overflow-auto bg-[#050505] font-mono text-xs p-4 leading-relaxed selection:bg-[#D99A45]/30">
          <div className="min-w-full">
            {filteredLines.map(({ line, originalIdx }: { line: string; originalIdx: number }) => (
              <div
                key={originalIdx}
                className="flex items-start group hover:bg-[#121212] py-0.5 rounded px-1 transition-colors"
              >
                <span className="w-12 shrink-0 select-none text-[11px] text-[#404040] group-hover:text-[#D99A45] text-right pr-4 font-mono">
                  {originalIdx}
                </span>
                <span className="text-[#E0E0E0] whitespace-pre-wrap break-all flex-1 font-mono">
                  {line || "\u00A0"}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* Footer info */}
        <div className="p-3 bg-[#0A0A0A] border-t border-[#1C1C1C] flex items-center justify-between text-[11px] text-[#71717A]">
          <div className="flex items-center gap-2">
            <Layers className="w-3.5 h-3.5 text-[#D99A45]" />
            <span>Retrieved Vector Chunk Grounding</span>
          </div>
          <span>Press ESC to close</span>
        </div>
      </div>
    </div>
  );
}
