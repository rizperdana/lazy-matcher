export const API_BASE = "/api/v1";

export interface MatchJob {
  id: string;
  batch_id: string;
  candidate_id: string;
  source_type: string;
  source_value: string;
  title: string | null;
  status: "pending" | "processing" | "completed" | "failed";
  attempt_count: number;
  queued_at: string;
  started_at: string | null;
  finished_at: string | null;
  error_code: string | null;
  error_message: string | null;
  score_overall: number | null;
  score_skills: number | null;
  score_experience: number | null;
  score_location: number | null;
  matched_skills: string[];
  missing_skills: string[];
  recommendation: string | null;
  years_experience: number | null;
  llm_model: string | null;
  created_at: string;
  updated_at: string;
}

export interface MatchBatchResponse {
  batch_id: string;
  job_count: number;
  jobs: MatchJob[];
}

export interface MatchJobListResponse {
  items: MatchJob[];
  total: number;
  limit: number;
  offset: number;
}

export async function submitBatch(items: string[], llmModel?: string): Promise<MatchBatchResponse> {
  const res = await fetch(`${API_BASE}/matches`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      items: items.map((content) => ({ content, ...(llmModel ? { llm_model: llmModel } : {}) })),
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Failed to submit batch");
  }
  return res.json();
}

export async function fetchJobs(params?: {
  status?: string;
  limit?: number;
  offset?: number;
}): Promise<MatchJobListResponse> {
  const searchParams = new URLSearchParams();
  if (params?.status) searchParams.set("status", params.status);
  if (params?.limit) searchParams.set("limit", String(params.limit));
  if (params?.offset) searchParams.set("offset", String(params.offset));

  const url = `${API_BASE}/matches?${searchParams.toString()}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error("Failed to fetch jobs");
  return res.json();
}

export async function fetchJob(id: string): Promise<MatchJob> {
  const res = await fetch(`${API_BASE}/matches/${id}`);
  if (!res.ok) throw new Error("Failed to fetch job");
  return res.json();
}
