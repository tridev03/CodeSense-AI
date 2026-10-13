"use client";

import { useState, useEffect, useCallback } from "react";
import { reposApi, RepositoryResponse } from "@/lib/api";
import { RepoCard } from "@/components/repo-card";
import { ConnectRepoDialog } from "@/components/connect-repo-dialog";
import { SkeletonCard } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { FolderGit2, Search, Layers, CheckCircle2, RefreshCw, AlertTriangle } from "lucide-react";
import { Input } from "@/components/ui/input";

export default function RepositoriesPage() {
  const [repos, setRepos] = useState<RepositoryResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");

  const fetchRepos = useCallback(async () => {
    try {
      setIsLoading(true);
      const res = await reposApi.list(0, 100);
      setRepos(res.items);
    } catch {
      // Handled via state
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchRepos();
  }, [fetchRepos]);

  const handleRepoCreated = (newRepo: RepositoryResponse) => {
    setRepos((prev) => [newRepo, ...prev]);
  };

  const handleRepoDeleted = (id: string) => {
    setRepos((prev) => prev.filter((r) => r.id !== id));
  };

  const handleRepoUpdated = (updated: RepositoryResponse) => {
    setRepos((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
  };

  const filteredRepos = repos.filter(
    (r) =>
      r.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (r.description && r.description.toLowerCase().includes(searchQuery.toLowerCase())) ||
      r.url.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // Statistics
  const totalCount = repos.length;
  const indexedCount = repos.filter((r) => r.status === "indexed").length;
  const inProgressCount = repos.filter((r) => r.status === "cloning" || r.status === "indexing").length;
  const failedCount = repos.filter((r) => r.status === "failed").length;

  return (
    <div className="space-y-8 max-w-7xl mx-auto pb-16">
      {/* Page Title & Connect Action */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-light text-[#F5F5F5] tracking-tight">Repositories</h1>
          <p className="text-xs text-[#71717A] mt-1">
            Manage your connected codebases, trigger Qdrant vector indexing, and explore citations.
          </p>
        </div>
        <ConnectRepoDialog onRepoCreated={handleRepoCreated} />
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-[#101010] border border-[#242424] rounded-2xl p-4 flex items-center justify-between">
          <div>
            <p className="text-xs text-[#71717A]">Total Repositories</p>
            <p className="text-2xl font-light text-[#F5F5F5] mt-1">{totalCount}</p>
          </div>
          <div className="w-10 h-10 rounded-xl bg-[#080808] border border-[#242424] flex items-center justify-center text-[#A1A1AA]">
            <FolderGit2 className="w-5 h-5" />
          </div>
        </div>

        <div className="bg-[#101010] border border-[#242424] rounded-2xl p-4 flex items-center justify-between">
          <div>
            <p className="text-xs text-[#71717A]">Indexed</p>
            <p className="text-2xl font-light text-[#22C55E] mt-1">{indexedCount}</p>
          </div>
          <div className="w-10 h-10 rounded-xl bg-[#080808] border border-[#242424] flex items-center justify-center text-[#22C55E]">
            <CheckCircle2 className="w-5 h-5" />
          </div>
        </div>

        <div className="bg-[#101010] border border-[#242424] rounded-2xl p-4 flex items-center justify-between">
          <div>
            <p className="text-xs text-[#71717A]">Indexing In-Flight</p>
            <p className="text-2xl font-light text-[#D99A45] mt-1">{inProgressCount}</p>
          </div>
          <div className="w-10 h-10 rounded-xl bg-[#080808] border border-[#242424] flex items-center justify-center text-[#D99A45]">
            <RefreshCw className={`w-5 h-5 ${inProgressCount > 0 ? "animate-spin" : ""}`} />
          </div>
        </div>

        <div className="bg-[#101010] border border-[#242424] rounded-2xl p-4 flex items-center justify-between">
          <div>
            <p className="text-xs text-[#71717A]">Failed</p>
            <p className="text-2xl font-light text-[#EF4444] mt-1">{failedCount}</p>
          </div>
          <div className="w-10 h-10 rounded-xl bg-[#080808] border border-[#242424] flex items-center justify-center text-[#EF4444]">
            <AlertTriangle className="w-5 h-5" />
          </div>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex items-center gap-3">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-[#71717A]" />
          <Input
            placeholder="Filter repositories by name, URL or description..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-10 bg-[#0D0D0D] border-[#242424] text-[#F5F5F5] placeholder:text-[#52525B] focus:border-[#D99A45] focus:ring-[#D99A45]/20 h-10 rounded-xl text-xs"
          />
        </div>
      </div>

      {/* Grid List */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          <SkeletonCard className="h-64" />
          <SkeletonCard className="h-64" />
          <SkeletonCard className="h-64" />
        </div>
      ) : filteredRepos.length === 0 ? (
        repos.length === 0 ? (
          <EmptyState
            icon={<FolderGit2 className="w-8 h-8" />}
            title="No repositories connected"
            description="Connect your GitHub or local git repository to index symbols and enable grounded AI assistance."
            action={<ConnectRepoDialog onRepoCreated={handleRepoCreated} />}
          />
        ) : (
          <div className="text-center py-16 bg-[#0D0D0D] border border-[#242424] rounded-2xl">
            <p className="text-sm text-[#A1A1AA]">No repositories matching &quot;{searchQuery}&quot;</p>
          </div>
        )
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {filteredRepos.map((repo) => (
            <RepoCard
              key={repo.id}
              repo={repo}
              onDelete={handleRepoDeleted}
              onUpdate={handleRepoUpdated}
            />
          ))}
        </div>
      )}
    </div>
  );
}

