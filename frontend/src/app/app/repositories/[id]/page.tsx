"use client";

import { useState, useEffect, useCallback, use } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { reposApi, RepositoryResponse, IndexingJobResponse, BASE_URL } from "@/lib/api";
import { StatusBadge } from "@/components/ui/status-badge";
import { toast } from "sonner";
import {
  ArrowLeft,
  FolderGit2,
  GitBranch,
  FileCode,
  Layers,
  MessageSquare,
  Search,
  Play,
  Trash2,
  Calendar,
  Clock,
  Loader2,
  CheckCircle2,
  AlertCircle,
  ExternalLink,
  Award,
} from "lucide-react";
import { GitHistoryViewer } from "@/components/git-history-viewer";

function GithubIcon({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
    </svg>
  );
}
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Progress } from "@/components/ui/progress";
import { SkeletonCard } from "@/components/ui/skeleton";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function RepositoryDetailPage({ params }: PageProps) {
  const { id } = use(params);
  const router = useRouter();
  const [repo, setRepo] = useState<RepositoryResponse | null>(null);
  const [indexingJob, setIndexingJob] = useState<IndexingJobResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isTriggering, setIsTriggering] = useState(false);

  const fetchRepoData = useCallback(async () => {
    try {
      const [repoData, statusData] = await Promise.all([
        reposApi.get(id),
        reposApi.status(id),
      ]);
      setRepo(repoData);
      setIndexingJob(statusData);
    } catch {
      toast.error("Repository not found");
      router.push("/app/repositories");
    } finally {
      setIsLoading(false);
    }
  }, [id, router]);

  useEffect(() => {
    fetchRepoData();
  }, [fetchRepoData]);

  // Polling / SSE streaming when indexing is active
  useEffect(() => {
    let interval: NodeJS.Timeout;
    const isWorking =
      repo?.status === "indexing" ||
      repo?.status === "cloning" ||
      indexingJob?.status === "running" ||
      indexingJob?.status === "pending";

    if (isWorking) {
      interval = setInterval(async () => {
        try {
          const status = await reposApi.status(id);
          if (status) {
            setIndexingJob(status);
            if (status.status === "completed" || status.status === "failed") {
              const updatedRepo = await reposApi.get(id);
              setRepo(updatedRepo);
            }
          }
        } catch {
          // Silent catch in polling loop
        }
      }, 3000);
    }

    let eventSource: EventSource | null = null;
    if (isWorking && typeof window !== "undefined") {
      try {
        eventSource = new EventSource(`${BASE_URL}/repositories/${id}/status/stream`);
        eventSource.onmessage = async (e) => {
          if (!e.data || e.data === "null") return;
          try {
            const status = JSON.parse(e.data);
            if (status && !status.error) {
              setIndexingJob(status);
              if (status.status === "completed" || status.status === "failed") {
                eventSource?.close();
                const updatedRepo = await reposApi.get(id);
                setRepo(updatedRepo);
              }
            }
          } catch {
            // Silent catch
          }
        };
        eventSource.onerror = () => {
          eventSource?.close();
        };
      } catch {
        // Fallback to interval
      }
    }

    return () => {
      if (interval) clearInterval(interval);
      if (eventSource) eventSource.close();
    };
  }, [repo?.status, indexingJob?.status, id]);

  const handleTriggerIndex = async () => {
    try {
      setIsTriggering(true);
      await reposApi.index(id);
      toast.success("Indexing initiated");
      const updated = await reposApi.get(id);
      setRepo(updated);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to trigger indexing";
      toast.error(msg);
    } finally {
      setIsTriggering(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm(`Are you sure you want to delete ${repo?.name}?`)) return;
    try {
      await reposApi.delete(id);
      toast.success("Repository deleted");
      router.push("/app/repositories");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to delete repository";
      toast.error(msg);
    }
  };

  if (isLoading || !repo) {
    return (
      <div className="space-y-6 max-w-5xl mx-auto">
        <SkeletonCard className="h-48" />
        <SkeletonCard className="h-96" />
      </div>
    );
  }

  const isGithub = repo.source_type === "github" || repo.url.includes("github.com");

  return (
    <div className="space-y-8 max-w-5xl mx-auto pb-16">
      {/* Back button */}
      <div>
        <Link
          href="/app/repositories"
          className="inline-flex items-center gap-2 text-xs text-[#71717A] hover:text-[#D99A45] transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Back to Repositories
        </Link>
      </div>

      {/* Main Header Card */}
      <div className="bg-[#0D0D0D] border border-[#242424] rounded-2xl p-7 shadow-xl">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="flex items-start gap-4">
            <div className="w-14 h-14 rounded-2xl bg-[#141414] border border-[#303030] flex items-center justify-center text-[#D99A45] shrink-0">
              {isGithub ? <GithubIcon className="w-7 h-7" /> : <FolderGit2 className="w-7 h-7" />}
            </div>
            <div>
              <div className="flex items-center gap-3 flex-wrap">
                <h1 className="text-2xl font-light text-[#F5F5F5] tracking-tight">{repo.name}</h1>
                <StatusBadge status={repo.status} />
              </div>
              <p className="text-xs text-[#71717A] mt-1 font-mono truncate max-w-md">
                {repo.url}
              </p>
              {repo.description && (
                <p className="text-xs text-[#A1A1AA] mt-2 max-w-2xl leading-relaxed">
                  {repo.description}
                </p>
              )}
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-2.5 flex-wrap">
            <Link href={`/app/chat/${repo.id}`}>
              <Button className="bg-[#D99A45] hover:bg-[#D99A45]/90 text-black font-medium text-xs h-9 px-4 rounded-xl gap-2">
                <MessageSquare className="w-3.5 h-3.5" />
                Ask Codebase
              </Button>
            </Link>
            <Link href={`/app/search/${repo.id}`}>
              <Button
                variant="outline"
                className="bg-[#141414] border-[#242424] hover:bg-[#1A1A1A] hover:border-[#D99A45]/40 text-[#F5F5F5] text-xs h-9 px-4 rounded-xl gap-2"
              >
                <Search className="w-3.5 h-3.5" />
                Search
              </Button>
            </Link>
            <Link href={`/app/repositories/${repo.id}/eval`}>
              <Button
                variant="outline"
                className="bg-[#141414] border-[#242424] hover:bg-[#1A1A1A] hover:border-[#D99A45]/40 text-[#F5F5F5] text-xs h-9 px-3 rounded-xl gap-1.5"
              >
                <Award className="w-3.5 h-3.5 text-[#D99A45]" />
                Evaluation
              </Button>
            </Link>
            <Button
              variant="outline"
              onClick={handleTriggerIndex}
              disabled={isTriggering || repo.status === "indexing" || repo.status === "cloning"}
              className="bg-[#141414] border-[#242424] hover:bg-[#1A1A1A] text-[#F5F5F5] text-xs h-9 px-3 rounded-xl gap-1.5"
            >
              {isTriggering ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Play className="w-3.5 h-3.5" />
              )}
              Re-index
            </Button>
            <Button
              variant="ghost"
              onClick={handleDelete}
              className="text-[#71717A] hover:text-[#EF4444] hover:bg-[#141414] h-9 w-9 p-0 rounded-xl"
            >
              <Trash2 className="w-4 h-4" />
            </Button>
          </div>
        </div>

        {/* Quick Stats Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-8 pt-6 border-t border-[#1C1C1C]">
          <div>
            <span className="text-[11px] text-[#71717A] uppercase tracking-wider block">Branch</span>
            <span className="text-sm text-[#F5F5F5] font-mono flex items-center gap-1.5 mt-1">
              <GitBranch className="w-3.5 h-3.5 text-[#D99A45]" />
              {repo.branch || "main"}
            </span>
          </div>
          <div>
            <span className="text-[11px] text-[#71717A] uppercase tracking-wider block">Indexed Files</span>
            <span className="text-sm text-[#F5F5F5] flex items-center gap-1.5 mt-1">
              <FileCode className="w-3.5 h-3.5 text-[#A1A1AA]" />
              {repo.file_count ?? 0}
            </span>
          </div>
          <div>
            <span className="text-[11px] text-[#71717A] uppercase tracking-wider block">Embeddings</span>
            <span className="text-sm text-[#D99A45] flex items-center gap-1.5 mt-1 font-mono">
              <Layers className="w-3.5 h-3.5" />
              {repo.chunk_count ?? 0} vectors
            </span>
          </div>
          <div>
            <span className="text-[11px] text-[#71717A] uppercase tracking-wider block">Registered</span>
            <span className="text-sm text-[#71717A] flex items-center gap-1.5 mt-1">
              <Calendar className="w-3.5 h-3.5" />
              {new Date(repo.created_at).toLocaleDateString()}
            </span>
          </div>
        </div>
      </div>

      {/* Tabs */}
      <Tabs defaultValue="indexing" className="w-full">
        <TabsList className="bg-[#0D0D0D] border border-[#242424] rounded-xl p-1 mb-6">
          <TabsTrigger
            value="indexing"
            className="data-[state=active]:bg-[#D99A45] data-[state=active]:text-black text-xs text-[#A1A1AA] rounded-lg px-4"
          >
            Indexing Status
          </TabsTrigger>
          <TabsTrigger
            value="git"
            className="data-[state=active]:bg-[#D99A45] data-[state=active]:text-black text-xs text-[#A1A1AA] rounded-lg px-4"
          >
            Git History
          </TabsTrigger>
          <TabsTrigger
            value="metadata"
            className="data-[state=active]:bg-[#D99A45] data-[state=active]:text-black text-xs text-[#A1A1AA] rounded-lg px-4"
          >
            Metadata & System
          </TabsTrigger>
        </TabsList>

        <TabsContent value="indexing" className="space-y-6">
          <div className="bg-[#101010] border border-[#242424] rounded-2xl p-6">
            <h3 className="text-sm font-medium text-[#F5F5F5] mb-4">Latest Ingestion Job</h3>
            {indexingJob ? (
              <div className="space-y-5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <StatusBadge status={indexingJob.status} />
                    <span className="text-xs text-[#71717A]">
                      Step: <strong className="text-[#F5F5F5]">{indexingJob.current_step || "Idle"}</strong>
                    </span>
                  </div>
                  <span className="text-xs font-mono text-[#D99A45]">
                    {Math.round(indexingJob.progress)}%
                  </span>
                </div>

                <Progress
                  value={indexingJob.progress}
                  className="h-2 bg-[#080808] [&>div]:bg-[#D99A45]"
                />

                <div className="grid grid-cols-2 sm:grid-cols-3 gap-4 pt-4 border-t border-[#1C1C1C] text-xs">
                  <div>
                    <span className="text-[#71717A] block">Files Processed</span>
                    <span className="text-[#F5F5F5] font-mono mt-0.5 block">
                      {indexingJob.files_processed} / {indexingJob.files_total}
                    </span>
                  </div>
                  <div>
                    <span className="text-[#71717A] block">Chunks Created</span>
                    <span className="text-[#F5F5F5] font-mono mt-0.5 block">
                      {indexingJob.chunks_created}
                    </span>
                  </div>
                  <div>
                    <span className="text-[#71717A] block">Started At</span>
                    <span className="text-[#71717A] mt-0.5 block">
                      {indexingJob.started_at
                        ? new Date(indexingJob.started_at).toLocaleTimeString()
                        : "N/A"}
                    </span>
                  </div>
                </div>

                {indexingJob.status === "failed" && indexingJob.error_message && (
                  <div className="p-3 bg-[#1F0A0A] border border-[#EF4444]/30 rounded-xl flex items-center gap-2.5 text-xs text-[#EF4444]">
                    <AlertCircle className="w-4 h-4 shrink-0" />
                    <span>{indexingJob.error_message}</span>
                  </div>
                )}
              </div>
            ) : (
              <p className="text-xs text-[#71717A]">No indexing jobs have been run yet.</p>
            )}
          </div>
        </TabsContent>

        <TabsContent value="git" className="space-y-6">
          <GitHistoryViewer repositoryId={repo.id} branch={repo.branch || undefined} />
        </TabsContent>

        <TabsContent value="metadata" className="space-y-6">
          <div className="bg-[#101010] border border-[#242424] rounded-2xl p-6 space-y-4 text-xs">
            <div className="flex justify-between py-2 border-b border-[#1A1A1A]">
              <span className="text-[#71717A]">Repository ID</span>
              <span className="font-mono text-[#A1A1AA]">{repo.id}</span>
            </div>
            <div className="flex justify-between py-2 border-b border-[#1A1A1A]">
              <span className="text-[#71717A]">Source Type</span>
              <span className="uppercase text-[#A1A1AA]">{repo.source_type}</span>
            </div>
            <div className="flex justify-between py-2 border-b border-[#1A1A1A]">
              <span className="text-[#71717A]">Commit Hash</span>
              <span className="font-mono text-[#D99A45]">
                {repo.commit_hash ? repo.commit_hash.slice(0, 8) : "HEAD"}
              </span>
            </div>
            <div className="flex justify-between py-2">
              <span className="text-[#71717A]">Last Updated</span>
              <span className="text-[#A1A1AA]">
                {new Date(repo.updated_at).toLocaleString()}
              </span>
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
