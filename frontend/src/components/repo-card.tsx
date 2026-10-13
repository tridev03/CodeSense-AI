"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { RepositoryResponse, IndexingJobResponse, reposApi } from "@/lib/api";
import { StatusBadge } from "@/components/ui/status-badge";
import { toast } from "sonner";
import {
  FolderGit2,
  GitBranch,
  FileCode,
  Layers,
  MessageSquare,
  Search,
  Play,
  Trash2,
  Loader2,
  ExternalLink,
} from "lucide-react";

function GithubIcon({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
    </svg>
  );
}
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

interface RepoCardProps {
  repo: RepositoryResponse;
  onDelete: (id: string) => void;
  onUpdate: (repo: RepositoryResponse) => void;
}

export function RepoCard({ repo, onDelete, onUpdate }: RepoCardProps) {
  const [isIndexing, setIsIndexing] = useState(
    repo.status === "cloning" || repo.status === "indexing"
  );
  const [jobStatus, setJobStatus] = useState<IndexingJobResponse | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);

  // Poll indexing status if active
  useEffect(() => {
    let interval: NodeJS.Timeout;

    if (isIndexing) {
      const checkStatus = async () => {
        try {
          const status = await reposApi.status(repo.id);
          if (status) {
            setJobStatus(status);
            if (status.status === "completed") {
              setIsIndexing(false);
              toast.success(`Indexing completed for ${repo.name}`);
              const updated = await reposApi.get(repo.id);
              onUpdate(updated);
            } else if (status.status === "failed") {
              setIsIndexing(false);
              toast.error(`Indexing failed: ${status.error_message || "Unknown error"}`);
              const updated = await reposApi.get(repo.id);
              onUpdate(updated);
            }
          }
        } catch {
          // Silent catch in polling loop
        }
      };

      checkStatus();
      interval = setInterval(checkStatus, 3000);
    }

    return () => {
      if (interval) clearInterval(interval);
    };
  }, [isIndexing, repo.id, repo.name, onUpdate]);

  const handleTriggerIndex = async () => {
    try {
      setIsIndexing(true);
      await reposApi.index(repo.id);
      toast.info(`Indexing triggered for ${repo.name}`);
    } catch (err: unknown) {
      setIsIndexing(false);
      const msg = err instanceof Error ? err.message : "Failed to trigger indexing";
      toast.error(msg);
    }
  };

  const handleDelete = async () => {
    try {
      setIsDeleting(true);
      await reposApi.delete(repo.id);
      toast.success(`Repository ${repo.name} removed`);
      onDelete(repo.id);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to delete repository";
      toast.error(msg);
    } finally {
      setIsDeleting(false);
      setShowDeleteDialog(false);
    }
  };

  const isGithub = repo.source_type === "github" || repo.url.includes("github.com");

  return (
    <>
      <div className="group bg-[#101010] hover:bg-[#141414] border border-[#242424] hover:border-[#303030] rounded-2xl p-6 transition-all duration-200 flex flex-col justify-between relative hover:-translate-y-0.5 shadow-lg shadow-black/40">
        <div>
          {/* Top row: Icon + Name + Status */}
          <div className="flex items-start justify-between gap-3 mb-3">
            <div className="flex items-center gap-3 min-w-0">
              <div className="w-10 h-10 rounded-xl bg-[#080808] border border-[#242424] flex items-center justify-center text-[#D99A45] shrink-0 group-hover:border-[#D99A45]/30 transition-colors">
                {isGithub ? <GithubIcon className="w-5 h-5" /> : <FolderGit2 className="w-5 h-5" />}
              </div>
              <div className="min-w-0">
                <Link
                  href={`/app/repositories/${repo.id}`}
                  className="font-medium text-[#F5F5F5] hover:text-[#D99A45] transition-colors truncate block text-base"
                >
                  {repo.name}
                </Link>
                <div className="flex items-center gap-1.5 text-xs text-[#71717A] mt-0.5 truncate">
                  <GitBranch className="w-3 h-3 shrink-0" />
                  <span className="truncate">{repo.branch || "main"}</span>
                </div>
              </div>
            </div>
            <StatusBadge status={repo.status} />
          </div>

          {/* Description */}
          {repo.description ? (
            <p className="text-xs text-[#A1A1AA] line-clamp-2 mb-4 leading-relaxed">
              {repo.description}
            </p>
          ) : (
            <p className="text-xs text-[#52525B] italic mb-4">No description provided</p>
          )}

          {/* URL & Stats */}
          <div className="flex flex-wrap items-center gap-4 py-3 border-y border-[#1A1A1A] mb-4 text-xs text-[#71717A]">
            <div className="flex items-center gap-1.5">
              <FileCode className="w-3.5 h-3.5 text-[#A1A1AA]" />
              <span>{repo.file_count ?? 0} files</span>
            </div>
            <div className="flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5 text-[#D99A45]" />
              <span>{repo.chunk_count ?? 0} chunks</span>
            </div>
          </div>

          {/* Indexing Progress Bar */}
          {isIndexing && (
            <div className="space-y-1.5 mb-4 p-3 bg-[#080808] border border-[#242424] rounded-xl">
              <div className="flex justify-between items-center text-xs">
                <span className="text-[#D99A45] flex items-center gap-1.5">
                  <Loader2 className="w-3 h-3 animate-spin" />
                  {jobStatus?.current_step || "Processing..."}
                </span>
                <span className="text-[#A1A1AA] font-mono">
                  {Math.round(jobStatus?.progress ?? 0)}%
                </span>
              </div>
              <Progress
                value={jobStatus?.progress ?? 10}
                className="h-1.5 bg-[#141414] [&>div]:bg-[#D99A45]"
              />
            </div>
          )}
        </div>

        {/* Action Buttons */}
        <div className="flex items-center justify-between gap-2 pt-2">
          <div className="flex items-center gap-2">
            <Link href={`/app/chat/${repo.id}`}>
              <Button
                variant="outline"
                size="sm"
                className="bg-[#0D0D0D] border-[#242424] hover:bg-[#1A1A1A] hover:border-[#D99A45]/40 text-[#F5F5F5] rounded-xl text-xs h-8 px-3 gap-1.5 transition-colors"
              >
                <MessageSquare className="w-3.5 h-3.5 text-[#D99A45]" />
                Chat
              </Button>
            </Link>
            <Link href={`/app/search/${repo.id}`}>
              <Button
                variant="outline"
                size="sm"
                className="bg-[#0D0D0D] border-[#242424] hover:bg-[#1A1A1A] hover:border-[#D99A45]/40 text-[#F5F5F5] rounded-xl text-xs h-8 px-3 gap-1.5 transition-colors"
              >
                <Search className="w-3.5 h-3.5 text-[#A1A1AA]" />
                Search
              </Button>
            </Link>
          </div>

          <div className="flex items-center gap-1.5">
            {repo.status !== "indexing" && repo.status !== "cloning" && (
              <Button
                variant="ghost"
                size="sm"
                onClick={handleTriggerIndex}
                disabled={isIndexing}
                title="Index repository"
                className="text-[#A1A1AA] hover:text-[#D99A45] hover:bg-[#141414] rounded-lg h-8 w-8 p-0"
              >
                <Play className="w-3.5 h-3.5" />
              </Button>
            )}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowDeleteDialog(true)}
              title="Delete repository"
              className="text-[#71717A] hover:text-[#EF4444] hover:bg-[#141414] rounded-lg h-8 w-8 p-0"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </Button>
          </div>
        </div>
      </div>

      {/* Delete Confirmation Modal */}
      <Dialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <DialogContent className="bg-[#0D0D0D] border border-[#242424] text-[#F5F5F5] sm:max-w-[400px] rounded-2xl">
          <DialogHeader>
            <DialogTitle className="text-lg font-light text-[#EF4444]">
              Delete Repository
            </DialogTitle>
            <DialogDescription className="text-xs text-[#A1A1AA]">
              Are you sure you want to delete <span className="font-semibold text-white">&quot;{repo.name}&quot;</span>? This will permanently remove all associated vector embeddings and indexing jobs.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="gap-2 sm:gap-0 mt-4">
            <Button
              variant="outline"
              onClick={() => setShowDeleteDialog(false)}
              className="border-[#242424] bg-transparent text-[#A1A1AA] hover:bg-[#141414] rounded-xl text-xs h-9"
            >
              Cancel
            </Button>
            <Button
              onClick={handleDelete}
              disabled={isDeleting}
              className="bg-[#EF4444] hover:bg-[#EF4444]/90 text-white rounded-xl text-xs h-9"
            >
              {isDeleting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
