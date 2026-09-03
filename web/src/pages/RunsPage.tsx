import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../api";
import type { RunSummary } from "../types";

export const STATUS_LABEL: Record<string, string> = {
  pending: "排队中",
  running: "运行中",
  done: "完成",
  error: "错误",
};

export default function RunsPage() {
  const { suiteId } = useParams();
  const [runs, setRuns] = useState<RunSummary[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    setRuns(null);
    setLoadError(null);
    api<RunSummary[]>(`/suites/${suiteId}/runs`)
      .then(setRuns)
      .catch((e) => setLoadError((e as Error).message));
  }, [suiteId]);

  if (loadError) return <div className="error-box">加载失败：{loadError}</div>;
  if (!runs) return <p className="muted">加载中…</p>;

  return (
    <>
      <h1>运行历史</h1>
      <table>
        <thead>
          <tr><th>Run</th><th>状态</th><th>通过</th><th>时间</th></tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.id}>
              <td><Link to={`/runs/${r.id}`} className="mono">#{r.id}</Link></td>
              <td>
                <span className={`badge ${r.status === "done" ? "ok" : r.status === "error" ? "bad" : ""}`}>
                  {STATUS_LABEL[r.status] ?? r.status}
                </span>
              </td>
              <td>{r.summary ? `${r.summary.passed}/${r.summary.total}` : "—"}</td>
              <td className="muted mono">{r.created_at.slice(0, 19).replace("T", " ")}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {runs.length === 0 && <p className="muted">还没有运行记录。</p>}
    </>
  );
}
