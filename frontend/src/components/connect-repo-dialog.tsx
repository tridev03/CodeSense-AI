"use client";

import { useState } from "react";
import { reposApi, RepositoryCreate, RepositoryResponse } from "@/lib/api";
import { toast } from "sonner";
import { Plus, FolderGit2, Loader2, GitBranch } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

function GithubIcon({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
    </svg>
  );
}

interface ConnectRepoDialogProps {
  onRepoCreated: (repo: RepositoryResponse) => void;
  trigger?: React.ReactNode;
}

export function ConnectRepoDialog({ onRepoCreated, trigger }: ConnectRepoDialogProps) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [branch, setBranch] = useState("main");
  const [description, setDescription] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const validateUrlOrPath = (inputUrl: string): string | null => {
    const trimmed = inputUrl.trim();
    if (trimmed.startsWith("http://")) {
      return "Insecure HTTP is not allowed. Please use HTTPS (https://github.com/...)";
    }
    if (trimmed.startsWith("https://")) {
      const githubRegex = /^https:\/\/(www\.)?github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+(\.git)?\/?$/;
      if (!githubRegex.test(trimmed)) {
        return "Please enter a valid GitHub repository URL (e.g., https://github.com/owner/repo)";
      }
      if (/localhost|127\.|192\.168\.|10\.|172\.(1[6-9]|2[0-9]|3[0-1])\.|169\.254\./i.test(trimmed)) {
        return "Internal and private network destinations are blocked for security.";
      }
    }
    return null;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !url.trim()) {
      toast.error("Repository name and URL/path are required");
      return;
    }

    const validationError = validateUrlOrPath(url);
    if (validationError) {
      toast.error(validationError);
      return;
    }

    try {
      setIsSubmitting(true);
      const payload: RepositoryCreate = {
        name: name.trim(),
        url: url.trim(),
        branch: branch.trim() || "main",
        description: description.trim() || undefined,
      };

      const newRepo = await reposApi.create(payload);
      toast.success(`Repository "${newRepo.name}" connected!`);
      onRepoCreated(newRepo);
      setOpen(false);
      resetForm();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to connect repository";
      toast.error(msg);
    } finally {
      setIsSubmitting(false);
    }
  };

  const resetForm = () => {
    setName("");
    setUrl("");
    setBranch("main");
    setDescription("");
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger className="inline-flex items-center justify-center font-medium bg-[#D99A45] hover:bg-[#D99A45]/90 text-black text-sm h-10 px-4 rounded-xl gap-2 transition-all shadow-lg shadow-[#D99A45]/10">
        {trigger ?? (
          <>
            <Plus className="w-4 h-4" />
            Connect Repository
          </>
        )}
      </DialogTrigger>
      <DialogContent className="bg-[#0D0D0D] border border-[#242424] text-[#F5F5F5] sm:max-w-[480px] rounded-2xl p-6">
        <DialogHeader>
          <div className="w-10 h-10 rounded-xl bg-[#141414] border border-[#303030] flex items-center justify-center text-[#D99A45] mb-2">
            <FolderGit2 className="w-5 h-5" />
          </div>
          <DialogTitle className="text-xl font-light tracking-tight">Connect Repository</DialogTitle>
          <DialogDescription className="text-xs text-[#71717A]">
            Provide a GitHub remote URL or a local folder path on the server.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 mt-2">
          <div className="space-y-1.5">
            <Label htmlFor="repo-name" className="text-xs text-[#A1A1AA] uppercase tracking-wider">
              Repository Name
            </Label>
            <Input
              id="repo-name"
              placeholder="e.g. backend-core"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="bg-[#080808] border-[#242424] text-[#F5F5F5] placeholder:text-[#52525B] focus:border-[#D99A45] focus:ring-[#D99A45]/20 rounded-xl h-10"
              required
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="repo-url" className="text-xs text-[#A1A1AA] uppercase tracking-wider">
              Repository URL or Local Path
            </Label>
            <div className="relative">
              <GithubIcon className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#71717A]" />
              <Input
                id="repo-url"
                placeholder="https://github.com/org/repo or /path/to/repo"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                className="pl-9 bg-[#080808] border-[#242424] text-[#F5F5F5] placeholder:text-[#52525B] focus:border-[#D99A45] focus:ring-[#D99A45]/20 rounded-xl h-10"
                required
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="repo-branch" className="text-xs text-[#A1A1AA] uppercase tracking-wider">
              Default Branch
            </Label>
            <div className="relative">
              <GitBranch className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#71717A]" />
              <Input
                id="repo-branch"
                placeholder="main"
                value={branch}
                onChange={(e) => setBranch(e.target.value)}
                className="pl-9 bg-[#080808] border-[#242424] text-[#F5F5F5] placeholder:text-[#52525B] focus:border-[#D99A45] focus:ring-[#D99A45]/20 rounded-xl h-10"
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="repo-desc" className="text-xs text-[#A1A1AA] uppercase tracking-wider">
              Description <span className="text-[#52525B]">(Optional)</span>
            </Label>
            <Textarea
              id="repo-desc"
              placeholder="Brief summary of this codebase..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="bg-[#080808] border-[#242424] text-[#F5F5F5] placeholder:text-[#52525B] focus:border-[#D99A45] focus:ring-[#D99A45]/20 rounded-xl resize-none h-20 text-xs"
            />
          </div>

          <div className="flex justify-end gap-2.5 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
              className="border-[#242424] bg-transparent text-[#A1A1AA] hover:bg-[#141414] hover:text-[#F5F5F5] rounded-xl text-xs h-10"
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={isSubmitting}
              className="bg-[#D99A45] hover:bg-[#D99A45]/90 text-black font-medium rounded-xl text-xs h-10 px-5"
            >
              {isSubmitting ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 mr-2 animate-spin" />
                  Connecting...
                </>
              ) : (
                "Save & Connect"
              )}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

