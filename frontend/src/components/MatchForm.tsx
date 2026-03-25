"use client";

import { useState, useCallback, FormEvent } from "react";
import styles from "./MatchForm.module.css";

interface Props {
  onSubmit: (items: string[], llmModel: string) => void;
  isSubmitting: boolean;
  error: string | null;
}

export function MatchForm({ onSubmit, isSubmitting, error }: Props) {
  const [text, setText] = useState("");
  const [llmModel, setLlmModel] = useState("gemini");

  const validate = useCallback((input: string): { items: string[]; errors: string[] } => {
    const lines = input.split("\n");
    const errors: string[] = [];
    const seen = new Set<string>();
    const cleaned: string[] = [];

    lines.forEach((line, idx) => {
      const value = line.trim();
      if (!value) return;
      if (seen.has(value.toLowerCase())) {
        errors.push(`Line ${idx + 1}: duplicate entry`);
        return;
      }
      seen.add(value.toLowerCase());
      cleaned.push(value);
    });

    if (cleaned.length === 0) errors.push("Add at least 1 job description.");
    if (cleaned.length > 10) errors.push("Maximum 10 items per batch.");

    cleaned.forEach((value, idx) => {
      if (value.length < 10) errors.push(`Line ${idx + 1}: too short to score.`);
      if (value.length > 50000) errors.push(`Line ${idx + 1}: too long.`);
    });

    return { items: cleaned, errors };
  }, []);

  const { items, errors } = validate(text);
  const hasErrors = errors.length > 0;

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (hasErrors || isSubmitting) return;
    onSubmit(items, llmModel);
    setText("");
  };

  const pickRandom = <T,>(arr: T[], count: number): T[] => {
    const shuffled = [...arr].sort(() => Math.random() - 0.5);
    return shuffled.slice(0, Math.max(1, count));
  };

  const generateRandom = () => {
    const titles = [
      "Senior Python Engineer", "Full-Stack Developer", "Staff Backend Engineer",
      "Frontend Developer", "DevOps Engineer", "Data Engineer", "ML Engineer",
      "iOS Developer", "Android Developer", "Platform Engineer", "SRE",
      "Tech Lead", "Engineering Manager", "QA Engineer", "Security Engineer",
      "Cloud Architect", "Database Administrator", "Mobile Developer",
      "React Native Developer", "Go Developer", "Rust Developer",
      "Java Engineer", "C++ Engineer", "Embedded Systems Engineer",
      "Blockchain Developer", "Game Developer", "BI Analyst",
      "Solutions Architect", "API Developer", "Infrastructure Engineer",
    ];
    const skills = [
      "Python", "FastAPI", "Django", "Flask", "JavaScript", "TypeScript",
      "React", "Next.js", "Vue", "Angular", "Node.js", "PostgreSQL", "MySQL",
      "MongoDB", "Redis", "Docker", "Kubernetes", "AWS", "GCP", "Azure",
      "Terraform", "CI/CD", "GraphQL", "REST APIs", "gRPC", "Kafka",
      "RabbitMQ", "Elasticsearch", "Linux", "Go", "Rust", "Java", "Kotlin",
      "Swift", "React Native", "TensorFlow", "PyTorch", "Spark", "Airflow",
    ];
    const seniorities = ["Junior", "Mid-level", "Senior", "Staff", "Lead", "Principal"];
    const locations = [
      "Remote", "Hybrid", "On-site Singapore", "Remote (APAC)", "San Francisco",
      "New York", "London", "Berlin", "Tokyo", "Sydney", "Toronto", "Remote (EU only)",
    ];

    const count = Math.floor(Math.random() * 4) + 3; // 3-6 jobs
    const jobs = Array.from({ length: count }, () => {
      const title = titles[Math.floor(Math.random() * titles.length)];
      const pickedSkills = pickRandom(skills, Math.floor(Math.random() * 5) + 3);
      const seniority = seniorities[Math.floor(Math.random() * seniorities.length)];
      const years = Math.floor(Math.random() * 10) + 1;
      const location = locations[Math.floor(Math.random() * locations.length)];
      return `${seniority} ${title} — ${pickedSkills.join(", ")}. ${years}+ years. ${location}.`;
    });
    setText(jobs.join("\n"));
  };

  return (
    <form onSubmit={handleSubmit} className={styles.form}>
      <div className={styles.field}>
        <label htmlFor="descriptions">Job descriptions</label>
        <textarea
          id="descriptions"
          className={styles.textarea}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={"Paste 1–10 job descriptions or URLs, one per line.\n\nExample:\nSenior Python Engineer — 5+ years, FastAPI, PostgreSQL\nhttps://company.com/jobs/senior-backend"}
          spellCheck={false}
          rows={8}
        />
        <div className={styles.help}>One item per line. Text or URLs accepted.</div>
      </div>

      {hasErrors && (
        <div className={styles.validation}>
          <strong>Validation issues:</strong>
          {errors.slice(0, 4).map((e, i) => (
            <span key={i}> • {e}</span>
          ))}
          {errors.length > 4 && <span> • …</span>}
        </div>
      )}

      {!hasErrors && text.trim().length > 0 && (
        <div className={styles.validationOk}>
          Ready. {items.length} item(s) to submit.
        </div>
      )}

      {error && (
        <div className={styles.submitError}>
          <strong>Submission failed:</strong> {error}
        </div>
      )}

      <div className={styles.field}>
        <label htmlFor="llm-model">AI scoring model</label>
        <select
          id="llm-model"
          className={styles.textarea}
          value={llmModel}
          onChange={(e) => setLlmModel(e.target.value)}
          style={{ padding: "0.5rem", height: "auto" }}
        >
          <option value="gemini">Gemini (default)</option>
          <option value="openrouter">OpenRouter</option>
        </select>
        <div className={styles.help}>Select which LLM provider to use for scoring.</div>
      </div>

      <div className={styles.actions}>
        <button
          type="submit"
          className={styles.btnPrimary}
          disabled={hasErrors || isSubmitting}
        >
          {isSubmitting ? "Submitting..." : `Submit batch${items.length > 0 ? ` (${items.length})` : ""}`}
        </button>
        <button type="button" className={styles.btnGhost} onClick={() => setText("")}>
          Clear
        </button>
        <button type="button" className={styles.btnGhost} onClick={generateRandom}>
          Randomize
        </button>
      </div>
    </form>
  );
}
