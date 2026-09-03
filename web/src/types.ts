export interface Project {
  id: number;
  name: string;
  created_at: string;
}

export interface Suite {
  id: number;
  project_id: number;
  name: string;
  yaml_text: string;
  updated_at: string;
}

export interface RunSummary {
  id: number;
  suite_id: number;
  status: "pending" | "running" | "done" | "error";
  created_at: string;
  finished_at: string | null;
  summary: { total: number; passed: number; errors: number } | null;
}

export interface CaseDelta {
  case_id: string;
  old_score: number | null;
  new_score: number | null;
  change: "regression" | "improved" | "unchanged" | "new" | "removed" | "error";
}

export interface Comparison {
  has_regressions: boolean;
  has_errors: boolean;
  summary: string;
  deltas: CaseDelta[];
  baseline_run_id: number;
}

export interface EvalResult {
  evaluator: string;
  score: number;
  passed: boolean;
  detail: string;
  raw: string | null;
}

export interface CaseResult {
  case_id: string;
  status: "ok" | "error";
  output: string;
  evals: EvalResult[];
  score: number;
  passed: boolean;
  error: string | null;
}

export interface RunDetail extends RunSummary {
  error: string | null;
  result: { results: CaseResult[] } | null;
  comparison: Comparison | null;
  judge_changed: boolean;
}

export interface ValidateResult {
  ok: boolean;
  cases: { id: string; evaluator_count: number }[];
  error: string | null;
}
