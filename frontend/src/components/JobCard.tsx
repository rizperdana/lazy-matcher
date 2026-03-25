"use client";

import { type MatchJob } from "@/lib/api";
import styles from "./JobCard.module.css";

interface Props {
  job: MatchJob;
}

const STATUS_CONFIG = {
  pending: { label: "pending", dotClass: "info" },
  processing: { label: "processing", dotClass: "warn" },
  completed: { label: "completed", dotClass: "good" },
  failed: { label: "failed", dotClass: "bad" },
};

export function JobCard({ job }: Props) {
  const statusConf = STATUS_CONFIG[job.status] || STATUS_CONFIG.pending;

  const displayTitle = job.title || job.source_value.slice(0, 80);
  const timeAgo = getTimeAgo(job.created_at);

  return (
    <article className={styles.card} data-status={job.status}>
      <div className={styles.top}>
        <div>
          <h3 className={styles.title}>{displayTitle}</h3>
          <p className={styles.sub}>
            {job.id.slice(0, 8)} • {timeAgo} • {job.source_type}
          </p>
        </div>
        <span className={`${styles.badge} ${styles[job.status]}`}>
          <span className={`${styles.dot} ${styles[statusConf.dotClass]}`}></span>
          {statusConf.label}
        </span>
      </div>

      {/* Progress bar */}
      <div className={styles.progressWrap}>
        <div
          className={styles.progress}
          style={{
            width: job.status === "completed" || job.status === "failed"
              ? "100%"
              : job.status === "processing"
              ? "50%"
              : "10%",
          }}
        />
      </div>

          {/* Scores (visible when completed) */}
          {job.status === "completed" && job.score_overall !== null && (
            <>
              <div className={styles.stats}>
                <div className={styles.mini}>
                  <div className={styles.k}>Overall</div>
                  <div className={styles.v}>{job.score_overall}%</div>
                </div>
                <div className={styles.mini}>
                  <div className={styles.k}>Skills</div>
                  <div className={styles.v}>{job.score_skills ?? "--"}%</div>
                </div>
                <div className={styles.mini}>
                  <div className={styles.k}>Experience</div>
                  <div className={styles.v}>
                    {job.score_experience ?? "--"}%
                    {job.years_experience !== null && job.years_experience !== undefined && (
                      <span style={{ marginLeft: 4, opacity: 0.7 }}>({job.years_experience}y)</span>
                    )}
                  </div>
                </div>
                {job.llm_model && (
                  <div className={styles.mini}>
                    <div className={styles.k}>Model</div>
                    <div className={styles.v} style={{ fontSize: "0.7rem" }}>{job.llm_model}</div>
                  </div>
                )}
              </div>

          {/* Matched skills */}
          {job.matched_skills.length > 0 && (
            <div className={styles.contentBox}>
              <h4>Matched skills</h4>
              <div className={styles.tagList}>
                {job.matched_skills.map((s) => (
                  <span key={s} className={styles.tag}>{s}</span>
                ))}
              </div>
            </div>
          )}

          {/* Missing skills */}
          {job.missing_skills.length > 0 && (
            <div className={styles.contentBox}>
              <h4>Missing skills</h4>
              <div className={styles.tagList}>
                {job.missing_skills.map((s) => (
                  <span key={s} className={`${styles.tag} ${styles.missing}`}>{s}</span>
                ))}
              </div>
            </div>
          )}

          {/* Recommendation */}
          {job.recommendation && (
            <div className={styles.contentBox}>
              <h4>Recommendation</h4>
              <div className={styles.recommendation}>{job.recommendation}</div>
            </div>
          )}
        </>
      )}

      {/* Processing state */}
      {job.status === "processing" && (
        <div className={styles.contentBox}>
          <h4>Status</h4>
          <div className={styles.recommendation}>
            Worker is processing this job. Extracting requirements and computing scores...
          </div>
        </div>
      )}

      {/* Error state */}
      {job.status === "failed" && (
        <div className={styles.contentBox}>
          <h4>Error</h4>
          <div className={styles.errorText}>
            {job.error_message || "Processing failed. The job can be retried."}
          </div>
        </div>
      )}
    </article>
  );
}

function getTimeAgo(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}
