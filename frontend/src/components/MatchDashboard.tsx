"use client";

import { useState, useCallback, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { submitBatch, fetchJobs, type MatchJob } from "@/lib/api";
import { MatchForm } from "./MatchForm";
import { ResultsList } from "./ResultsList";
import { StatusSummary } from "./StatusSummary";
import styles from "./MatchDashboard.module.css";

function formatTime(date: Date): string {
  return `${date.getHours().toString().padStart(2, "0")}:${date.getMinutes().toString().padStart(2, "0")}:${date.getSeconds().toString().padStart(2, "0")}`;
}

export function MatchDashboard() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<string>("completed"); // Default to completed for scoring
  const [scoreFilter, setScoreFilter] = useState<number>(0);
  const [yearFilter, setYearFilter] = useState<number>(0);
  const [lastRefresh, setLastRefresh] = useState<Date | null>(null);

  // Initialize lastRefresh on client only to avoid hydration mismatch
  useEffect(() => {
    setLastRefresh(new Date());
  }, []);

  // Poll jobs list
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["jobs", statusFilter],
    queryFn: () => fetchJobs({ status: statusFilter || undefined, limit: 50 }),
    refetchInterval: 3000,
    refetchIntervalInBackground: true,
  });

  // Submit batch mutation
  const mutation = useMutation({
    mutationFn: (params: { items: string[]; llmModel: string }) =>
      submitBatch(params.items, params.llmModel),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      setLastRefresh(new Date());
    },
  });

  const handleSubmit = useCallback(
    (items: string[], llmModel: string) => {
      mutation.mutate({ items, llmModel });
    },
    [mutation]
  );

  const handleRefresh = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: ["jobs"] });
    setLastRefresh(new Date());
  }, [queryClient]);

  const jobs = (data?.items ?? []).filter((j) => {
    // Always apply status filter first
    if (statusFilter && j.status !== statusFilter) return false;
    // Score and YoE filters only apply to completed jobs
    if (j.status === "completed") {
      if (scoreFilter > 0 && (j.score_overall ?? 0) < scoreFilter) return false;
      if (yearFilter > 0 && (j.years_experience ?? 0) < yearFilter) return false;
    }
    return true;
  });

  // Compute status counts
  const counts = {
    pending: jobs.filter((j) => j.status === "pending").length,
    processing: jobs.filter((j) => j.status === "processing").length,
    completed: jobs.filter((j) => j.status === "completed").length,
    failed: jobs.filter((j) => j.status === "failed").length,
  };

  return (
    <div className={styles.shell}>
      {/* Header */}
      <header className={styles.topbar}>
        <div className={styles.brand}>
          <div className={styles.brandMark}>
            <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M5 7.5C5 5.567 6.567 4 8.5 4h7C17.433 4 19 5.567 19 7.5v9c0 1.933-1.567 3.5-3.5 3.5h-7C6.567 20 5 18.433 5 16.5v-9Z" stroke="white" strokeWidth="1.8"/>
              <path d="M8 9h8M8 12h5M8 15h6" stroke="white" strokeWidth="1.8" strokeLinecap="round"/>
            </svg>
          </div>
          <div>
            <h1>Lazy Matcher</h1>
            <p>Async scoring pipeline for job descriptions</p>
          </div>
        </div>
        <div className={styles.topMeta}>
          <span className={styles.pill}>
            <span className={`${styles.dot} ${styles.good}`}></span> API online
          </span>
          <span className={styles.pill}>
            <span className={`${styles.dot} ${styles.info}`}></span> 2 workers
          </span>
          <span className={styles.pill}>
            <span className={`${styles.dot} ${styles.warn}`}></span> Polling every 3s
          </span>
        </div>
      </header>

      <div className={styles.grid}>
        {/* Submit section */}
        <section className={styles.card}>
          <div className={styles.cardHeader}>
            <div>
              <h2>Submit match batch</h2>
              <p>Accepts 1–10 job descriptions (text or URLs)</p>
            </div>
          </div>
          <div className={styles.cardBody}>
            <MatchForm
              onSubmit={handleSubmit}
              isSubmitting={mutation.isPending}
              error={mutation.error?.message ?? null}
            />
            <StatusSummary counts={counts} total={data?.total ?? 0} />
          </div>
        </section>

        {/* Results section */}
        <section className={`${styles.card} ${styles.cardWide}`}>
          <div className={styles.cardHeader}>
            <div>
              <h2>Results</h2>
              <p>
                Last refreshed: {lastRefresh ? formatTime(lastRefresh) : "—"} • {data?.total ?? 0} total
              </p>
            </div>
            <div className={styles.row}>
              <select
                className={styles.select}
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                aria-label="Status filter"
              >
                <option value="completed">Completed only</option>
                <option value="pending">Pending</option>
                <option value="processing">Processing</option>
                <option value="failed">Failed</option>
                <option value="">All statuses</option>
              </select>
              <label className={styles.pill} style={{ gap: "0.4rem", cursor: "default" }}>
                <span>Min score %:</span>
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={scoreFilter || ""}
                  onChange={(e) => setScoreFilter(e.target.value ? Number(e.target.value) : 0)}
                  placeholder="0"
                  className={styles.textInput}
                />
              </label>
              <label className={styles.pill} style={{ gap: "0.4rem", cursor: "default" }}>
                <span>Min YoE:</span>
                <input
                  type="number"
                  min={0}
                  max={30}
                  value={yearFilter || ""}
                  onChange={(e) => setYearFilter(e.target.value ? Number(e.target.value) : 0)}
                  placeholder="0"
                  className={styles.textInput}
                />
              </label>
              <button className={styles.btnSecondary} onClick={handleRefresh}>
                Refresh
              </button>
            </div>
          </div>

          {/* Scoring Methodology Info */}
          <div className={styles.infoBox}>
            <details>
              <summary className={styles.infoSummary}>
                <span>How scores are calculated</span>
              </summary>
              <div className={styles.infoContent}>
                <p><strong>Overall Score = Skills 50% + Experience 30% + Location 20%</strong></p>
                <ul>
                  <li><strong>Skills (50%):</strong> Percentage of required technical skills found in the job description. Higher is better — more matching skills means stronger candidate fit.</li>
                  <li><strong>Experience (30%):</strong> Years of experience required by the job. Score is based on how well the candidate's experience matches (70-100% for 5+ years, lower for junior roles).</li>
                  <li><strong>Location (20%):</strong> Location preference match. Remote = 100%, Hybrid = 80%, On-site in candidate's area = 70%, Other = 50-60%.</li>
                </ul>
                <p className={styles.muted}>Scores are computed by AI (Gemini or OpenRouter) based on job description analysis. Filter by Min score % to find best matches.</p>
              </div>
            </details>
          </div>
          <div className={styles.cardBody}>
            {isError && (
              <div className={styles.errorBox}>
                <strong>Network error</strong>
                <p>{error?.message || "Failed to fetch results"}</p>
                <p className={styles.muted}>Stale data shown. Will retry automatically.</p>
              </div>
            )}
            {isLoading && jobs.length === 0 && (
              <div className={styles.emptyState}>
                <strong>Loading...</strong>
                <p>Fetching match results...</p>
              </div>
            )}
            {!isLoading && jobs.length === 0 && !isError && (
              <div className={styles.emptyState}>
                <strong>No results yet</strong>
                <p>Submit a batch of job descriptions to get started.</p>
              </div>
            )}
            <ResultsList jobs={jobs} />
          </div>
        </section>
      </div>
    </div>
  );
}
