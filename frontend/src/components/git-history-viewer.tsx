"use client";

import { useState, useEffect, useCallback } from "react";
import { gitApi, GitCommitItem } from "@/lib/api";
import { toast } from "sonner";
import {
  GitCommit,
  GitBranch,
  Search,
  Copy,
  Check,
  ChevronDown,
  ChevronUp,
  FileCode,
  Calendar,
  User,
  Loader2,
  RefreshCw,
  Clock,
  Sparkles,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";

interface GitHistoryViewerProps {
  repositoryId: string;
  branch?: string;
}

export function GitHistoryViewer({ repositoryId, branch = "main" }: GitHistoryViewerProps) {
  const [commits, setCommits] = useState<GitCommitItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [isSearching, setIsSearching] = useState(false);
  const [expandedCommit, setExpandedCommit] = useState<string | null>(null);
  const [copiedHash, setCopiedHash] = useState<string | null>(null);

  const fetchCommits = useCallback(async () => {
    setIsLoading(true);
    try {
      const res = await gitApi.listCommits(repositoryId, 50, branch);
      setCommits(res.commits || []);
    } catch {
      // Backend may not have local git repo cloned yet or git endpoints returned fallback
      setCommits([]);
    } finally {
      setIsLoading(false);
    }
  }, [repositoryId, branch]);

  useEffect(() => {
    fetchCommits();
  }, [fetchCommits]);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) {
      fetchCommits();
      return;
    }

    setIsSearching(true);
    try {
      const res = await gitApi.search(repositoryId, {
        query: searchQuery.trim(),
        top_k: 30,
      });
      // Convert git search items or filter
      const filtered = commits.filter(
        (c) =>
          c.message.toLowerCase().includes(searchQuery.toLowerCase()) ||
          c.author_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
          c.hash.toLowerCase().includes(searchQuery.toLowerCase())
      );
      if (filtered.length > 0) {
        setCommits(filtered);
      } else if (res.results && res.results.length > 0) {
        // Fallback or search results
        toast.info(`Found ${res.results.length} related code chunks for "${searchQuery}"`);
      } else {
        setCommits([]);
      }
    } catch {
      // Local filter fallback
      const filtered = commits.filter(
        (c) =>
          c.message.toLowerCase().includes(searchQuery.toLowerCase()) ||
          c.author_name.toLowerCase().includes(searchQuery.toLowerCase())
      );
      setCommits(filtered);
    } finally {
      setIsSearching(false);
    }
  };

  const copyHash = (hash: string, shortHash: string) => {
    navigator.clipboard.writeText(hash);
    setCopiedHash(hash);
    toast.success(`Copied commit ${shortHash}`);
    setTimeout(() => setCopiedHash(null), 2000);
  };

  const getInitials = (name: string) => {
    if (!name) return "AI";
    return name
      .split(" ")
      .map((n) => n[0])
      .slice(0, 2)
      .join("")
      .toUpperCase();
  };

  return (
    <div className="space-y-6">
      {/* Top Search & Actions Bar */}
      <div className="bg-[#101010] border border-[#242424] rounded-2xl p-4 flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
        <form onSubmit={handleSearch} className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#71717A]" />
          <Input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search commits by message, author, or SHA..."
            className="pl-9 bg-[#080808] border-[#242424] text-xs h-9 text-[#F5F5F5] placeholder:text-[#71717A] focus-visible:border-[#D99A45]"
          />
        </form>

        <div className="flex items-center gap-2">
          <Badge
            variant="outline"
            className="bg-[#080808] border-[#242424] text-[#A1A1AA] text-xs font-mono h-9 px-3 gap-1.5"
          >
            <GitBranch className="w-3.5 h-3.5 text-[#D99A45]" />
            {branch}
          </Badge>
          <Button
            variant="outline"
            onClick={fetchCommits}
            disabled={isLoading}
            className="bg-[#080808] border-[#242424] hover:bg-[#1A1A1A] text-[#F5F5F5] text-xs h-9 px-3 gap-1.5"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </div>

      {/* Commit List Feed */}
      <div className="bg-[#101010] border border-[#242424] rounded-2xl overflow-hidden">
        <div className="px-6 py-4 border-b border-[#1C1C1C] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <GitCommit className="w-4 h-4 text-[#D99A45]" />
            <h3 className="text-sm font-medium text-[#F5F5F5]">Commit History</h3>
          </div>
          <span className="text-xs text-[#71717A] font-mono">
            {commits.length} commit{commits.length === 1 ? "" : "s"}
          </span>
        </div>

        {isLoading ? (
          <div className="p-12 flex flex-col items-center justify-center space-y-3">
            <Loader2 className="w-6 h-6 animate-spin text-[#D99A45]" />
            <p className="text-xs text-[#A1A1AA]">Reading Git repository history...</p>
          </div>
        ) : commits.length === 0 ? (
          <div className="p-12 text-center space-y-3">
            <div className="w-12 h-12 rounded-full bg-[#1A1A1A] border border-[#242424] flex items-center justify-center mx-auto text-[#71717A]">
              <GitCommit className="w-6 h-6" />
            </div>
            <h4 className="text-sm font-medium text-[#F5F5F5]">No commits recorded</h4>
            <p className="text-xs text-[#71717A] max-w-sm mx-auto">
              {searchQuery
                ? `No commits matched "${searchQuery}". Clear your search to see all commits.`
                : "Commits will be indexed once repository cloning and ingestion complete."}
            </p>
            {searchQuery && (
              <Button
                variant="outline"
                onClick={() => {
                  setSearchQuery("");
                  fetchCommits();
                }}
                className="bg-[#141414] border-[#242424] text-xs text-[#F5F5F5] h-8 mt-2"
              >
                Clear Search
              </Button>
            )}
          </div>
        ) : (
          <div className="divide-y divide-[#1C1C1C]">
            {commits.map((commit) => {
              const isExpanded = expandedCommit === commit.hash;
              const hasDetails = (commit.changed_files && commit.changed_files.length > 0) || commit.diff_summary;

              return (
                <div
                  key={commit.hash}
                  className="p-4 sm:p-5 hover:bg-[#141414]/50 transition-colors"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex items-start gap-3.5 min-w-0">
                      {/* Avatar */}
                      <div className="w-8 h-8 rounded-full bg-gradient-to-br from-[#242424] to-[#121212] border border-[#D99A45]/30 flex items-center justify-center text-[10px] font-medium text-[#D99A45] shrink-0 mt-0.5 shadow-[0_0_10px_rgba(217,154,69,0.1)]">
                        {getInitials(commit.author_name)}
                      </div>

                      {/* Content */}
                      <div className="min-w-0 space-y-1">
                        <div className="flex items-center gap-2 flex-wrap">
                          <p className="text-sm font-medium text-[#F5F5F5] truncate max-w-xl">
                            {commit.message}
                          </p>
                        </div>

                        <div className="flex items-center gap-3 text-xs text-[#71717A] flex-wrap">
                          <span className="flex items-center gap-1 text-[#A1A1AA]">
                            <User className="w-3 h-3 text-[#71717A]" />
                            {commit.author_name || "Unknown Author"}
                          </span>
                          <span className="flex items-center gap-1">
                            <Clock className="w-3 h-3 text-[#71717A]" />
                            {commit.date
                              ? new Date(commit.date).toLocaleDateString(undefined, {
                                  month: "short",
                                  day: "numeric",
                                  year: "numeric",
                                  hour: "2-digit",
                                  minute: "2-digit",
                                })
                              : "Recent"}
                          </span>
                          {commit.changed_files && commit.changed_files.length > 0 && (
                            <span className="text-[#D99A45]/80 font-mono text-[11px]">
                              {commit.changed_files.length} file{commit.changed_files.length === 1 ? "" : "s"}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Actions */}
                    <div className="flex items-center gap-2 shrink-0">
                      <button
                        onClick={() => copyHash(commit.hash, commit.short_hash || commit.hash.slice(0, 7))}
                        title="Copy full SHA"
                        className="font-mono text-xs text-[#A1A1AA] hover:text-[#D99A45] bg-[#0A0A0A] hover:bg-[#1A1A1A] border border-[#242424] px-2.5 py-1 rounded-lg flex items-center gap-1.5 transition-colors"
                      >
                        {commit.short_hash || commit.hash.slice(0, 7)}
                        {copiedHash === commit.hash ? (
                          <Check className="w-3 h-3 text-emerald-400" />
                        ) : (
                          <Copy className="w-3 h-3 text-[#71717A]" />
                        )}
                      </button>

                      {hasDetails && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setExpandedCommit(isExpanded ? null : commit.hash)}
                          className="text-[#71717A] hover:text-[#F5F5F5] h-8 w-8 p-0"
                        >
                          {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                        </Button>
                      )}
                    </div>
                  </div>

                  {/* Expanded Changed Files & Diff */}
                  {isExpanded && hasDetails && (
                    <div className="mt-4 pt-3 border-t border-[#1C1C1C] pl-11 space-y-3">
                      {commit.changed_files && commit.changed_files.length > 0 && (
                        <div>
                          <span className="text-[11px] text-[#71717A] uppercase tracking-wider block mb-2 font-mono">
                            Changed Files
                          </span>
                          <div className="flex flex-wrap gap-1.5">
                            {commit.changed_files.map((file, idx) => (
                              <Badge
                                key={idx}
                                variant="outline"
                                className="bg-[#0A0A0A] border-[#242424] text-[#A1A1AA] text-[11px] font-mono py-0.5 px-2 gap-1.5"
                              >
                                <FileCode className="w-3 h-3 text-[#D99A45]" />
                                {file}
                              </Badge>
                            ))}
                          </div>
                        </div>
                      )}

                      {commit.diff_summary && (
                        <div className="bg-[#0A0A0A] border border-[#1C1C1C] rounded-xl p-3 font-mono text-[11px] text-[#A1A1AA] whitespace-pre-wrap max-h-48 overflow-y-auto">
                          {commit.diff_summary}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

