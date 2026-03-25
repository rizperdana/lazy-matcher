"use client";

import { useState, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { submitBatch, fetchJobs, type MatchJob } from "@/lib/api";
import { MatchForm } from "./MatchForm";
import { ResultsList } from "./ResultsList";
import { StatusSummary } from "./StatusSummary";
import styles from "./MatchDashboard.module.css";

export function MatchDashboard() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [scoreFilter, setScoreFilter] = useState<number>(0);
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());

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

  const jobs = (data?.items ?? []).filter((j) =>
    scoreFilter > 0 && j.status === "completed"
      ? (j.score_overall ?? 0) >= scoreFilter
      : true
  );

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
                Last refreshed: {lastRefresh.toLocaleTimeString()} • {data?.total ?? 0} total
              </p>
            </div>
            <div className={styles.row}>
              <select
                className={styles.select}
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                aria-label="Status filter"
              >
                <option value="">All statuses</option>
                <option value="pending">pending</option>
                <option value="processing">processing</option>
                <option value="completed">completed</option>
                <option value="failed">failed</option>
              </select>
              <label className={styles.pill} style={{ gap: "0.4rem", cursor: "default" }}>
                <span>Min score:</span>
                <input
                  type="range"
                  min={0}
                  max={100}
                  step={5}
                  value={scoreFilter}
                  onChange={(e) => setScoreFilter(Number(e.target.value))}
                  style={{ width: "80px", accentColor: "var(--accent)" }}
                />
                <span style={{ minWidth: "2.5rem", textAlign: "right" }}>
                  {scoreFilter > 0 ? `${scoreFilter}%` : "off"}
                </span>
              </label>
              <button className={styles.btnSecondary} onClick={handleRefresh}>
                Refresh
              </button>
            </div>
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
