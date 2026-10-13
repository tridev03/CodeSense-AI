"use client";

import { useState, useEffect, use } from "react";
import Link from "next/link";
import { searchApi, reposApi, RepositoryResponse, SearchResultItem } from "@/lib/api";
import { toast } from "sonner";
import {
  ArrowLeft,
  Search,
  Filter,
  FileCode,
  Layers,
  Code2,
  BookOpen,
  Settings2,
  Copy,
  Check,
  Loader2,
  Sparkles,
  Maximize2,
} from "lucide-react";
import { CitationInspector } from "@/components/citation-inspector";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { SkeletonCard } from "@/components/ui/skeleton";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function RepositorySearchPage({ params }: PageProps) {
  const { id } = use(params);
  const [repo, setRepo] = useState<RepositoryResponse | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResultItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [retrievalMode, setRetrievalMode] = useState<"hybrid" | "vector_only" | "bm25_only">("hybrid");
  const [useReranker, setUseReranker] = useState(true);
  const [languageFilter, setLanguageFilter] = useState("");
  const [contentType, setContentType] = useState<string>("all");
  const [copiedChunkId, setCopiedChunkId] = useState<string | null>(null);
  const [inspectingItem, setInspectingItem] = useState<SearchResultItem | null>(null);

  useEffect(() => {
    reposApi.get(id).then(setRepo).catch(() => {});
  }, [id]);

  const handleSearch = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!query.trim()) return;

    try {
      setIsLoading(true);
      const res = await searchApi.search(id, {
        query: query.trim(),
        top_k: 15,
        retrieval_mode: retrievalMode,
        use_reranker: useReranker,
        language: languageFilter.trim() || undefined,
        content_type: contentType === "all" ? undefined : contentType,
      });
      setResults(res.results);
      if (res.results.length === 0) {
        toast.info("No matching chunks found for this query");
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Search failed";
      toast.error(msg);
    } finally {
      setIsLoading(false);
    }
  };

  const handleCopy = (content: string, chunkId: string) => {
    navigator.clipboard.writeText(content);
    setCopiedChunkId(chunkId);
    toast.success("Snippet copied");
    setTimeout(() => setCopiedChunkId(null), 2000);
  };

  return (
    <div className="space-y-6 max-w-5xl mx-auto pb-16">
      {/* Top Header */}
      <div className="flex items-center gap-3">
        <Link
          href={`/app/repositories/${id}`}
          className="text-[#71717A] hover:text-[#D99A45] transition-colors p-1"
        >
          <ArrowLeft className="w-4 h-4" />
        </Link>
        <div>
          <h1 className="text-xl font-light text-[#F5F5F5] tracking-tight">
            Code Search · {repo?.name || "Repository"}
          </h1>
          <p className="text-xs text-[#71717A] mt-0.5">
            Hybrid vector + BM25 keyword search powered by Qdrant
          </p>
        </div>
      </div>

      {/* Search Input Bar */}
      <div className="bg-[#0D0D0D] border border-[#242424] rounded-2xl p-4 shadow-xl space-y-4">
        <form onSubmit={handleSearch} className="flex gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-[#71717A]" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search code, functions, docs, or concepts (e.g. 'token generation' or 'verify_password')..."
              className="pl-10 bg-[#080808] border-[#242424] text-[#F5F5F5] placeholder:text-[#52525B] focus:border-[#D99A45] focus:ring-[#D99A45]/20 h-11 rounded-xl text-sm"
            />
          </div>
          <Button
            type="submit"
            disabled={isLoading || !query.trim()}
            className="bg-[#D99A45] hover:bg-[#D99A45]/90 text-black font-medium h-11 px-5 rounded-xl text-xs gap-1.5 shrink-0"
          >
            {isLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Search className="w-3.5 h-3.5" />}
            Search
          </Button>
        </form>

        {/* Filter Chips & Controls */}
        <div className="flex flex-wrap items-center justify-between gap-4 pt-3 border-t border-[#1C1C1C] text-xs">
          {/* Mode Selector */}
          <div className="flex items-center gap-1.5">
            <span className="text-[#71717A] mr-1 flex items-center gap-1">
              <Filter className="w-3 h-3" /> Mode:
            </span>
            {(["hybrid", "vector_only", "bm25_only"] as const).map((m) => (
              <button
                key={m}
                onClick={() => setRetrievalMode(m)}
                className={`px-2.5 py-1 rounded-lg text-[11px] transition-colors ${
                  retrievalMode === m
                    ? "bg-[#D99A45] text-black font-medium"
                    : "bg-[#141414] text-[#A1A1AA] hover:text-white"
                }`}
              >
                {m === "hybrid" ? "Hybrid (RRF)" : m === "vector_only" ? "Vector" : "BM25"}
              </button>
            ))}
          </div>

          {/* Reranker switch */}
          <div className="flex items-center gap-2">
            <Switch
              id="reranker"
              checked={useReranker}
              onCheckedChange={setUseReranker}
              className="data-[state=checked]:bg-[#D99A45]"
            />
            <Label htmlFor="reranker" className="text-xs text-[#A1A1AA] cursor-pointer flex items-center gap-1">
              <Sparkles className="w-3 h-3 text-[#D99A45]" />
              BGE Reranking
            </Label>
          </div>
        </div>
      </div>

      {/* Results Section */}
      <div className="space-y-4">
        {isLoading ? (
          <div className="space-y-3">
            <SkeletonCard className="h-40" />
            <SkeletonCard className="h-40" />
          </div>
        ) : results.length === 0 ? (
          <div className="text-center py-20 bg-[#0D0D0D] border border-[#242424] rounded-2xl">
            <Code2 className="w-10 h-10 mx-auto opacity-20 mb-3 text-[#D99A45]" />
            <h3 className="text-sm font-medium text-[#F5F5F5]">Ready to search</h3>
            <p className="text-xs text-[#71717A] mt-1">
              Type keywords or semantic queries above to find code chunks across the codebase.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center justify-between text-xs text-[#71717A] px-1">
              <span>{results.length} code matches found</span>
              <span>Mode: {retrievalMode}</span>
            </div>

            {results.map((item) => (
              <div
                key={item.chunk_id}
                className="bg-[#0D0D0D] hover:bg-[#101010] border border-[#242424] hover:border-[#303030] rounded-2xl p-5 transition-colors space-y-3"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-2 flex-wrap">
                    <FileCode className="w-4 h-4 text-[#D99A45] shrink-0" />
                    <span className="font-mono text-xs text-[#F5F5F5] break-all">
                      {item.file_path}
                    </span>
                    {item.start_line && (
                      <Badge className="bg-[#141414] text-[#A1A1AA] border-[#242424] text-[10px] font-mono">
                        L{item.start_line}{item.end_line ? `-L${item.end_line}` : ""}
                      </Badge>
                    )}
                    {item.language && (
                      <Badge className="bg-[#1a1000] text-[#D99A45] border-[#D99A45]/30 text-[10px]">
                        {item.language}
                      </Badge>
                    )}
                  </div>

                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-[#71717A] font-mono">
                      Score: {item.score.toFixed(3)}
                    </span>
                    <button
                      onClick={() =>
                        setInspectingItem(item)
                      }
                      className="text-[#71717A] hover:text-[#D99A45] transition-colors p-1"
                      title="Inspect full code"
                    >
                      <Maximize2 className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={() => handleCopy(item.content, item.chunk_id)}
                      className="text-[#71717A] hover:text-[#D99A45] transition-colors p-1"
                      title="Copy code"
                    >
                      {copiedChunkId === item.chunk_id ? (
                        <Check className="w-3.5 h-3.5 text-[#22C55E]" />
                      ) : (
                        <Copy className="w-3.5 h-3.5" />
                      )}
                    </button>
                  </div>
                </div>

                {item.context_header && (
                  <p className="text-[11px] text-[#71717A] italic">
                    {item.context_header}
                  </p>
                )}

                <pre
                  onClick={() => setInspectingItem(item)}
                  title="Click to open code inspector"
                  className="p-3 bg-[#080808] border border-[#1A1A1A] hover:border-[#D99A45]/30 cursor-pointer rounded-xl text-xs font-mono text-[#D4D4D8] overflow-x-auto leading-relaxed transition-colors"
                >
                  <code>{item.content}</code>
                </pre>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Code Inspector Drawer */}
      <CitationInspector
        isOpen={!!inspectingItem}
        onClose={() => setInspectingItem(null)}
        citation={
          inspectingItem
            ? {
                file_path: inspectingItem.file_path,
                content: inspectingItem.content,
                chunk_id: inspectingItem.chunk_id,
                score: inspectingItem.score,
              }
            : null
        }
      />
    </div>
  );
}
