"use client";

import { useAuth } from "@/lib/auth-context";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import {
  User, Bell, Moon, Key, Globe, Cpu, Database, GitBranch, Shield, LogOut
} from "lucide-react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";

const SECTION_CLASS = "space-y-6";
const CARD_CLASS = "bg-[#0D0D0D] border border-[#242424] rounded-2xl p-6";
const LABEL_CLASS = "text-sm font-medium text-[#F5F5F5]";
const DESC_CLASS = "text-xs text-[#71717A] mt-0.5";
const ROW_CLASS = "flex items-start justify-between gap-4";

export default function SettingsPage() {
  const { user, logout, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !user) router.push("/login");
  }, [user, isLoading, router]);

  if (isLoading || !user) return null;

  return (
    <div className="min-h-screen bg-black">
      <div className="max-w-4xl mx-auto px-6 py-12">
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-2xl font-light text-[#F5F5F5] tracking-tight">Settings</h1>
          <p className="mt-1 text-sm text-[#71717A]">
            Manage your account, integrations, and retrieval configuration.
          </p>
        </div>

        <Tabs defaultValue="profile">
          <TabsList className="bg-[#0D0D0D] border border-[#242424] rounded-xl p-1 mb-8 flex-wrap gap-1 h-auto">
            {[
              { value: "profile", icon: User, label: "Profile" },
              { value: "retrieval", icon: Cpu, label: "Retrieval" },
              { value: "models", icon: Globe, label: "Models" },
              { value: "integrations", icon: GitBranch, label: "Integrations" },
              { value: "security", icon: Shield, label: "Security" },
            ].map(({ value, icon: Icon, label }) => (
              <TabsTrigger
                key={value}
                value={value}
                className="data-[state=active]:bg-[#D99A45] data-[state=active]:text-black text-[#A1A1AA] text-sm px-4 py-2 rounded-lg transition-all"
              >
                <Icon className="w-3.5 h-3.5 mr-1.5" />
                {label}
              </TabsTrigger>
            ))}
          </TabsList>

          {/* Profile */}
          <TabsContent value="profile" className={SECTION_CLASS}>
            <div className={CARD_CLASS}>
              <h3 className="text-[#F5F5F5] font-medium mb-6 flex items-center gap-2">
                <User className="w-4 h-4 text-[#D99A45]" /> Account
              </h3>
              <div className="space-y-4">
                <div>
                  <Label className={LABEL_CLASS}>Email address</Label>
                  <p className={DESC_CLASS}>Your registered email — cannot be changed.</p>
                  <Input
                    value={user.email}
                    readOnly
                    className="mt-2 bg-[#080808] border-[#242424] text-[#A1A1AA] cursor-not-allowed"
                  />
                </div>
                <div>
                  <Label className={LABEL_CLASS}>Account type</Label>
                  <div className="mt-2 flex items-center gap-2">
                    <Badge className="bg-[#1a1000] text-[#D99A45] border-[#D99A45]/30 border text-xs">
                      {user.is_superuser ? "Administrator" : "Developer"}
                    </Badge>
                    <span className="text-xs text-[#71717A]">
                      Since {new Date(user.created_at).toLocaleDateString()}
                    </span>
                  </div>
                </div>
              </div>
            </div>

            <div className={CARD_CLASS}>
              <h3 className="text-[#F5F5F5] font-medium mb-6 flex items-center gap-2">
                <Bell className="w-4 h-4 text-[#D99A45]" /> Preferences
              </h3>
              <div className="space-y-5">
                {[
                  { id: "notif-indexing", label: "Indexing notifications", desc: "Get notified when indexing completes or fails" },
                  { id: "notif-errors", label: "Error alerts", desc: "Receive alerts for failed queries or agent errors" },
                ].map((item) => (
                  <div key={item.id} className={ROW_CLASS}>
                    <div>
                      <Label htmlFor={item.id} className={LABEL_CLASS}>{item.label}</Label>
                      <p className={DESC_CLASS}>{item.desc}</p>
                    </div>
                    <Switch id={item.id} className="data-[state=checked]:bg-[#D99A45]" />
                  </div>
                ))}
              </div>
            </div>

            <div className={CARD_CLASS}>
              <button
                onClick={logout}
                className="flex items-center gap-2 text-sm text-[#EF4444] hover:text-[#FCA5A5] transition-colors"
              >
                <LogOut className="w-4 h-4" />
                Sign out of your account
              </button>
            </div>
          </TabsContent>

          {/* Retrieval */}
          <TabsContent value="retrieval" className={SECTION_CLASS}>
            <div className={CARD_CLASS}>
              <h3 className="text-[#F5F5F5] font-medium mb-6 flex items-center gap-2">
                <Database className="w-4 h-4 text-[#D99A45]" /> Retrieval Configuration
              </h3>
              <p className="text-xs text-[#71717A] mb-5">
                These are the backend defaults. Override per-query in the Chat or Search interfaces.
              </p>
              <div className="space-y-5">
                {[
                  {
                    id: "reranker",
                    label: "Enable BGE reranker",
                    desc: "Use cross-encoder reranking for higher precision (slower)",
                    defaultChecked: true,
                  },
                  {
                    id: "hybrid",
                    label: "Hybrid retrieval (recommended)",
                    desc: "Combine vector search + BM25 with RRF fusion",
                    defaultChecked: true,
                  },
                ].map((item) => (
                  <div key={item.id} className={ROW_CLASS}>
                    <div>
                      <Label htmlFor={item.id} className={LABEL_CLASS}>{item.label}</Label>
                      <p className={DESC_CLASS}>{item.desc}</p>
                    </div>
                    <Switch
                      id={item.id}
                      defaultChecked={item.defaultChecked}
                      className="data-[state=checked]:bg-[#D99A45]"
                    />
                  </div>
                ))}
                <Separator className="bg-[#242424]" />
                <div>
                  <Label className={LABEL_CLASS}>Default Top-K</Label>
                  <p className={DESC_CLASS}>Number of chunks to retrieve per query (default: 10)</p>
                  <Input
                    type="number"
                    defaultValue={10}
                    min={1}
                    max={50}
                    className="mt-2 w-24 bg-[#080808] border-[#242424] text-[#F5F5F5] focus:border-[#D99A45] focus:ring-[#D99A45]"
                  />
                </div>
              </div>
            </div>
          </TabsContent>

          {/* Models */}
          <TabsContent value="models" className={SECTION_CLASS}>
            <div className={CARD_CLASS}>
              <h3 className="text-[#F5F5F5] font-medium mb-6 flex items-center gap-2">
                <Cpu className="w-4 h-4 text-[#D99A45]" /> LLM Configuration
              </h3>
              <div className="space-y-4 text-sm">
                {[
                  { label: "LLM Provider", value: "Groq", note: "Configured in backend .env" },
                  { label: "Model", value: "qwen/qwen3-27b", note: "GROQ_MODEL" },
                  { label: "Embedding Model", value: "Qwen/Qwen3-Embedding-0.6B", note: "1024-dim vectors" },
                  { label: "Reranker", value: "BAAI/bge-reranker-base", note: "Cross-encoder" },
                ].map((item) => (
                  <div key={item.label} className="flex justify-between items-center py-3 border-b border-[#1A1A1A] last:border-0">
                    <div>
                      <span className="text-[#A1A1AA]">{item.label}</span>
                      <span className="ml-2 text-xs text-[#71717A]">{item.note}</span>
                    </div>
                    <Badge className="bg-[#0A0A0A] border border-[#303030] text-[#D99A45] text-xs font-mono">
                      {item.value}
                    </Badge>
                  </div>
                ))}
              </div>
              <p className="mt-4 text-xs text-[#71717A]">
                Model configuration is set via backend environment variables. These are read-only.
              </p>
            </div>
          </TabsContent>

          {/* Integrations */}
          <TabsContent value="integrations" className={SECTION_CLASS}>
            <div className={CARD_CLASS}>
              <h3 className="text-[#F5F5F5] font-medium mb-6 flex items-center gap-2">
                <GitBranch className="w-4 h-4 text-[#D99A45]" /> GitHub Integration
              </h3>
              <div className="space-y-4">
                <div>
                  <Label className={LABEL_CLASS}>GitHub Personal Access Token</Label>
                  <p className={DESC_CLASS}>
                    Required for private repositories. Set via <code className="text-[#D99A45] font-mono text-xs">GITHUB_TOKEN</code> in backend env.
                  </p>
                  <div className="mt-2 flex items-center gap-2">
                    <Input
                      type="password"
                      placeholder="ghp_••••••••••••••••"
                      readOnly
                      className="bg-[#080808] border-[#242424] text-[#71717A] cursor-not-allowed"
                    />
                    <Badge className="bg-[#0A0A0A] border border-[#242424] text-[#71717A] text-xs whitespace-nowrap">
                      Backend only
                    </Badge>
                  </div>
                </div>
                <Separator className="bg-[#242424]" />
                <div className={ROW_CLASS}>
                  <div>
                    <Label className={LABEL_CLASS}>Public repositories</Label>
                    <p className={DESC_CLASS}>Index public GitHub repositories without a token</p>
                  </div>
                  <Badge className="bg-[#003300] border border-[#00AA00]/30 text-[#00CC00] text-xs">Supported</Badge>
                </div>
                <div className={ROW_CLASS}>
                  <div>
                    <Label className={LABEL_CLASS}>Local filesystem paths</Label>
                    <p className={DESC_CLASS}>Index repositories cloned locally on the server</p>
                  </div>
                  <Badge className="bg-[#003300] border border-[#00AA00]/30 text-[#00CC00] text-xs">Supported</Badge>
                </div>
              </div>
            </div>
          </TabsContent>

          {/* Security */}
          <TabsContent value="security" className={SECTION_CLASS}>
            <div className={CARD_CLASS}>
              <h3 className="text-[#F5F5F5] font-medium mb-6 flex items-center gap-2">
                <Key className="w-4 h-4 text-[#D99A45]" /> Authentication
              </h3>
              <div className="space-y-4 text-sm">
                <div className="flex justify-between items-center">
                  <span className="text-[#A1A1AA]">Authentication method</span>
                  <Badge className="bg-[#1a1000] text-[#D99A45] border-[#D99A45]/30 border text-xs">JWT Bearer</Badge>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-[#A1A1AA]">Token expiry</span>
                  <span className="text-[#F5F5F5]">24 hours</span>
                </div>
                <div className="flex justify-between items-center">
                  <span className="text-[#A1A1AA]">Password hashing</span>
                  <Badge className="bg-[#0A0A0A] border border-[#303030] text-[#A1A1AA] text-xs">bcrypt</Badge>
                </div>
              </div>
              <Separator className="my-4 bg-[#242424]" />
              <div>
                <p className="text-xs text-[#71717A]">
                  To change your password, sign out and use the registration flow. 
                  Password reset is not yet implemented.
                </p>
              </div>
            </div>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}

