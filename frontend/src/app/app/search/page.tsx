"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { reposApi, RepositoryResponse } from "@/lib/api";
import { FolderGit2, Search, ArrowRight, Loader2 } from "lucide-react";
import { Input } from "@/components/ui/input";

export default function SearchIndexPage() {
  const [repos, setRepos] = useState<RepositoryResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    reposApi
      .list(0, 100)
      .then((res) => {
        setRepos(res.items);
      })
      .catch(() => {})
      .finally(() => {
        setIsLoading(false);
      });
  }, []);

  const indexedRepos = repos.filter((r) => r.status === "indexed");
  const filtered = indexedRepos.filter(
    (r) =>
      r.name.toLowerCase().includes(filter.toLowerCase()) ||
      (r.description && r.description.toLowerCase().includes(filter.toLowerCase()))
  );

  return (
    <div className="space-y-6 max-w-5xl mx-auto pb-16">
      <div>
        <h1 className="text-2xl font-light text-[#F5F5F5] tracking-tight">Code Search</h1>
        <p className="text-xs text-[#71717A] mt-1">
          Perform direct hybrid semantic and keyword search across indexed codebase chunks and functions.
        </p>
      </div>

      <div className="relative max-w-md">
        <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-[#71717A]" />
        <Input
          placeholder="Filter repositories..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="pl-10 bg-[#101010] border-[#242424] text-[#F5F5F5] placeholder:text-[#52525B] focus:border-[#D99A45] h-10 rounded-xl"
        />
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center p-12">
          <Loader2 className="w-6 h-6 text-[#D99A45] animate-spin" />
        </div>
      ) : indexedRepos.length === 0 ? (
        <div className="bg-[#101010] border border-[#242424] rounded-2xl p-8 text-center space-y-3">
          <FolderGit2 className="w-10 h-10 text-[#52525B] mx-auto" />
          <h3 className="text-sm font-medium text-white">No Indexed Repositories Available</h3>
          <p className="text-xs text-[#71717A] max-w-sm mx-auto">
            You need at least one fully indexed repository before you can run direct semantic code search.
          </p>
          <Link
            href="/app/repositories"
            className="inline-flex items-center gap-2 text-xs font-medium text-[#D99A45] hover:underline pt-2"
          >
            Go to Repositories <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {filtered.map((repo) => (
            <Link
              key={repo.id}
              href={`/app/search/${repo.id}`}
              className="group bg-[#101010] hover:bg-[#141414] border border-[#242424] hover:border-[#D99A45]/40 rounded-2xl p-5 transition-all flex flex-col justify-between"
            >
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    <div className="w-8 h-8 rounded-lg bg-[#181818] border border-[#2B2B2B] flex items-center justify-center text-[#D99A45]">
                      <FolderGit2 className="w-4 h-4" />
                    </div>
                    <span className="font-medium text-sm text-[#F5F5F5] group-hover:text-[#D99A45] transition-colors">
                      {repo.name}
                    </span>
                  </div>
                  <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                    Ready
                  </span>
                </div>
                <p className="text-xs text-[#71717A] line-clamp-2">
                  {repo.description || repo.url}
                </p>
              </div>

              <div className="pt-4 border-t border-[#1C1C1C] mt-4 flex items-center justify-between text-xs text-[#71717A]">
                <span>{repo.chunk_count ? `${repo.chunk_count} code chunks` : "Indexed"}</span>
                <span className="flex items-center gap-1 text-[#D99A45] group-hover:translate-x-0.5 transition-transform">
                  Search Code <ArrowRight className="w-3.5 h-3.5" />
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

