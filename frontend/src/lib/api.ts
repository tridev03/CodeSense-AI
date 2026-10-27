/**
 * Typed API client for the AI Knowledge Agent backend.
 * Base URL: NEXT_PUBLIC_API_URL (default: http://localhost:8000/api/v1)
 */

import axios, { AxiosError, AxiosRequestConfig } from "axios";

export const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

// ── axios instance ────────────────────────────────────────────────────────────
export const apiClient = axios.create({
  baseURL: BASE_URL,
  headers: { "Content-Type": "application/json" },
  timeout: 60_000,
});

// Attach Bearer token from localStorage on every request
apiClient.interceptors.request.use((cfg) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("access_token");
    if (token) cfg.headers.Authorization = `Bearer ${token}`;
  }
  return cfg;
});

// Normalize errors
apiClient.interceptors.response.use(
  (r) => r,
  (err: AxiosError<{ detail?: string }>) => {
    const detail = err.response?.data?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : detail
          ? JSON.stringify(detail)
          : err.message;
    return Promise.reject(new Error(message));
  }
);

// ── helpers ───────────────────────────────────────────────────────────────────
async function get<T>(url: string, cfg?: AxiosRequestConfig): Promise<T> {
  const r = await apiClient.get<T>(url, cfg);
  return r.data;
}
async function post<T>(url: string, data?: unknown, cfg?: AxiosRequestConfig): Promise<T> {
  const r = await apiClient.post<T>(url, data, cfg);
  return r.data;
}
async function patch<T>(url: string, data?: unknown, cfg?: AxiosRequestConfig): Promise<T> {
  const r = await apiClient.patch<T>(url, data, cfg);
  return r.data;
}
async function del<T = void>(url: string): Promise<T> {
  const r = await apiClient.delete<T>(url);
  return r.data;
}

// ── Auth ──────────────────────────────────────────────────────────────────────
export interface LoginRequest { email: string; password: string }
export interface TokenResponse { access_token: string; token_type: string; expires_in: number }
export interface UserCreate { email: string; password: string }
export interface UserResponse { id: string; email: string; is_active: boolean; is_superuser: boolean; created_at: string }

export const authApi = {
  login: (data: LoginRequest) => post<TokenResponse>("/auth/token", data),
  register: (data: UserCreate) => post<UserResponse>("/auth/register", data),
  me: () => get<UserResponse>("/auth/me"),
};

// ── Repositories ──────────────────────────────────────────────────────────────
export type RepositoryStatus = "pending" | "cloning" | "indexing" | "indexed" | "failed";
export type RepositorySourceType = "github" | "local";

export interface RepositoryCreate {
  name: string;
  url: string;
  branch?: string;
  description?: string;
}
export interface RepositoryResponse {
  id: string;
  name: string;
  description: string | null;
  url: string;
  source_type: RepositorySourceType;
  branch: string | null;
  commit_hash: string | null;
  status: RepositoryStatus;
  error_message: string | null;
  file_count: number | null;
  chunk_count: number | null;
  created_at: string;
  updated_at: string;
}
export interface RepositoryListResponse {
  items: RepositoryResponse[];
  total: number;
  skip: number;
  limit: number;
}

export type IndexingJobStatus = "pending" | "running" | "completed" | "failed";
export interface IndexingJobResponse {
  id: string;
  repository_id: string;
  status: IndexingJobStatus;
  progress: number;
  current_step: string | null;
  error_message: string | null;
  files_processed: number;
  files_total: number;
  chunks_created: number;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
}
export interface IndexTriggerResponse { job_id: string; repository_id: string; message: string }

export const reposApi = {
  list: (skip = 0, limit = 20) =>
    get<RepositoryListResponse>(`/repositories?skip=${skip}&limit=${limit}`),
  get: (id: string) => get<RepositoryResponse>(`/repositories/${id}`),
  create: (data: RepositoryCreate) => post<RepositoryResponse>("/repositories", data),
  delete: (id: string) => del(`/repositories/${id}`),
  index: (id: string) => post<IndexTriggerResponse>(`/repositories/${id}/index`),
  status: (id: string) => get<IndexingJobResponse | null>(`/repositories/${id}/status`),
};

// ── Search ────────────────────────────────────────────────────────────────────
export interface SearchRequest {
  query: string;
  top_k?: number;
  language?: string;
  content_type?: string;
  file_path?: string;
  retrieval_mode?: "vector_only" | "bm25_only" | "hybrid";
  use_reranker?: boolean;
}
export interface SearchResultItem {
  chunk_id: string;
  file_path: string;
  content_type: string;
  content: string;
  score: number;
  language?: string;
  start_line?: number;
  end_line?: number;
  symbol_type?: string;
  class_name?: string;
  function_name?: string;
  context_header?: string;
  section_title?: string;
  rerank_score?: number;
  retriever?: string;
}
export interface SearchResponse {
  query: string;
  repository_id: string;
  retrieval_mode: string;
  total_results: number;
  results: SearchResultItem[];
}

export const searchApi = {
  search: (repoId: string, data: SearchRequest) =>
    post<SearchResponse>(`/repositories/${repoId}/search`, data),
};

// ── Chat ──────────────────────────────────────────────────────────────────────
export interface Citation {
  file_path: string;
  start_line?: number;
  end_line?: number;
  symbol?: string;
  snippet?: string;
  content?: string;
  chunk_id?: string;
  score?: number;
}
export interface ChatRequest {
  query: string;
  top_k?: number;
  include_citations?: boolean;
  retrieval_mode?: "vector_only" | "bm25_only" | "hybrid";
  use_reranker?: boolean;
}
export interface ChatResponse {
  query: string;
  answer: string;
  repository_id: string;
  retrieval_mode: string;
  citations: Citation[];
  model: string;
  tokens_used?: number;
}

export const chatApi = {
  send: (repoId: string, data: ChatRequest) =>
    post<ChatResponse>(`/repositories/${repoId}/chat`, data),
};

// ── Agent ──────────────────────────────────────────────────────────────────────
export interface AgentQueryRequest {
  query: string;
  top_k?: number;
  max_reflections?: number;
  include_citations?: boolean;
}
export interface AgentToolCallLog { tool_name: string; query: string; result_count: number }
export interface AgentQueryResponse {
  query: string;
  repository_id: string;
  intent: string;
  answer: string;
  citations: Citation[];
  tool_calls: AgentToolCallLog[];
  reflection_count: number;
  tokens_used?: number;
  model: string;
}

export const agentApi = {
  query: (repoId: string, data: AgentQueryRequest) =>
    post<AgentQueryResponse>(`/repositories/${repoId}/agent/query`, data),
};

// ── Git Intelligence ───────────────────────────────────────────────────────────
export interface GitCommitItem {
  hash: string;
  short_hash: string;
  author_name: string;
  author_email: string;
  date: string;
  message: string;
  changed_files: string[];
  diff_summary?: string;
}
export interface GitCommitsResponse {
  repository_id: string;
  total_commits: number;
  commits: GitCommitItem[];
}
export interface GitSearchRequest {
  query: string;
  top_k?: number;
  author?: string;
  file_path?: string;
}
export interface GitSearchItem {
  chunk_id: string;
  commit_hash?: string;
  commit_author?: string;
  commit_date?: string;
  file_path: string;
  content: string;
  score: number;
}
export interface GitSearchResponse {
  query: string;
  repository_id: string;
  total_results: number;
  results: GitSearchItem[];
}
export interface GitFileHistoryRequest {
  file_path: string;
  top_k?: number;
}

export const gitApi = {
  listCommits: (repoId: string, limit = 50, branch?: string) =>
    get<GitCommitsResponse>(
      `/repositories/${repoId}/git/commits?limit=${limit}${
        branch ? `&branch=${encodeURIComponent(branch)}` : ""
      }`
    ),
  search: (repoId: string, data: GitSearchRequest) =>
    post<GitSearchResponse>(`/repositories/${repoId}/git/search`, data),
  fileHistory: (repoId: string, data: GitFileHistoryRequest) =>
    post<{ repository_id: string; file_path: string; commits: GitCommitItem[] }>(
      `/repositories/${repoId}/git/file-history`,
      data
    ),
};

// ── Evaluation ────────────────────────────────────────────────────────────────
export interface MetricScores {
  faithfulness: number;
  answer_relevance: number;
  context_recall: number;
  context_precision: number;
  hallucination_rate: number;
}
export interface QuestionEvaluationItem {
  question: string;
  ground_truth?: string;
  generated_answer: string;
  source_file?: string;
  retrieved_chunks_count: number;
  scores: MetricScores;
}
export interface GenerationEvalReport {
  repository_id: string;
  retrieval_mode: string;
  model: string;
  num_questions: number;
  aggregate_scores: MetricScores;
  per_question: QuestionEvaluationItem[];
  markdown_report: string;
  evaluated_at: string;
}
export interface GenerationEvalRequest {
  num_questions?: number;
  retrieval_mode?: string;
  top_k?: number;
  use_reranker?: boolean;
}

export const evalApi = {
  evaluateGeneration: (repoId: string, data: GenerationEvalRequest) =>
    post<GenerationEvalReport>(`/repositories/${repoId}/evaluate-generation`, data),
};

// ── Health & Status ────────────────────────────────────────────────────────────
export const healthApi = {
  check: () => get<{ status: string }>("/health"),
};

export interface SystemStatusResponse {
  backend: string;
  database: string;
  qdrant: string;
  redis: string;
  groq_configured: boolean;
  environment: string;
}

export const statusApi = {
  get: () => get<SystemStatusResponse>("/status"),
};

// ── Conversations & Messages (CHAT-01) ─────────────────────────────────────────
export interface MessageCreate {
  role: string;
  content: string;
  citations?: Citation[];
  model_name?: string;
  tokens_used?: number;
}

export interface MessageResponse {
  id: string;
  conversation_id: string;
  role: string;
  content: string;
  citations?: Citation[];
  model_name?: string;
  tokens_used?: number;
  created_at: string;
}

export interface ConversationCreate {
  title?: string;
  repository_id?: string;
}

export interface ConversationResponse {
  id: string;
  title: string;
  user_id?: string;
  repository_id?: string;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ConversationDetailResponse {
  id: string;
  title: string;
  user_id?: string;
  repository_id?: string;
  created_at: string;
  updated_at: string;
  messages: MessageResponse[];
}

export const conversationsApi = {
  list: (repositoryId?: string, skip = 0, limit = 50) =>
    get<ConversationResponse[]>(
      `/conversations?skip=${skip}&limit=${limit}${
        repositoryId ? `&repository_id=${repositoryId}` : ""
      }`
    ),
  create: (data: ConversationCreate) => post<ConversationResponse>("/conversations", data),
  get: (id: string) => get<ConversationDetailResponse>(`/conversations/${id}`),
  update: (id: string, data: { title: string }) => patch<ConversationResponse>(`/conversations/${id}`, data),
  delete: (id: string) => del(`/conversations/${id}`),
  addMessage: (id: string, data: MessageCreate) => post<MessageResponse>(`/conversations/${id}/messages`, data),
};



