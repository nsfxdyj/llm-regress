import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { api } from "../api";
import type { CaseDelta, RunDetail } from "../types";
import { STATUS_LABEL } from "./RunsPage";

export default function RunDetailPage() {
  const { runId } = useParams();
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [promoted, setPromoted] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [promoteError, setPromoteError] = useState<string | null>(null);

  useEffect(() => {
    setDetail(null);
    setLoadError(null);
    setPromoted(false);
    let timer: number | undefined;
    let cancelled = false;
    const load = () =>
      api<RunDetail>(`/runs/${runId}`)
        .then((d) => {
          if (cancelled) return;
          setDetail(d);
          setLoadError(null);
          if (d.status === "pending" || d.status === "running") {
            timer = window.setTimeout(load, 2000);
          }
        })
        .catch((e) => {
          if (!cancelled) setLoadError((e as Error).message);
        });
    load();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [runId]);

  if (loadError) return <div className="error-box">加载失败：{loadError}</div>;
  if (!detail) return <p className="muted">加载中…</p>;

  const deltaById = new Map<string, CaseDelta>(
    (detail.comparison?.deltas ?? []).map((d) => [d.case_id, d])
  );

  const promote = async () => {
    setPromoteError(null);
    try {
      await api(`/runs/${detail.id}/promote`, { method: "POST" });
      setPromoted(true);
    } catch (e) {
      setPromoteError((e as Error).message);
    }
  };

  return (
    <>
      <h1>
        Run #{detail.id}{" "}
        <span className={`badge ${detail.status === "done" ? "ok" : detail.status === "error" ? "bad" : ""}`}>
          {STATUS_LABEL[detail.status] ?? detail.status}
        </span>
      </h1>
      {detail.status === "error" && detail.error && <div className="error-box">{detail.error}</div>}
      {detail.judge_changed && (
        <div className="error-box">
          裁判模型已更换，与基线的对比已失效。确认无误后请把某次运行设为新基线。
        </div>
      )}
      {detail.comparison && (
        <p>
          对比基线（Run #{detail.comparison.baseline_run_id}）：
          <span className="mono"> {detail.comparison.summary}</span>
        </p>
      )}
      {detail.status === "done" && (
        <div className="row" style={{ margin: "12px 0" }}>
          <button onClick={promote} disabled={promoted}>
            {promoted ? "已设为基线" : "设为基线"}
          </button>
        </div>
      )}
      {promoteError && <div className="error-box">设为基线失败：{promoteError}</div>}
      {detail.result && (
        <table>
          <thead>
            <tr><th>用例</th><th>得分</th><th>对比</th><th>明细</th></tr>
          </thead>
          <tbody>
            {detail.result.results.map((r) => {
              const delta = deltaById.get(r.case_id);
              const isRegression = delta?.change === "regression";
              return (
                <tr key={r.case_id} style={isRegression ? { background: "#fbeeec" } : undefined}>
                  <td className="mono">{r.case_id}</td>
                  <td>
                    {r.status === "error" ? (
                      <span className="badge bad">错误</span>
                    ) : (
                      <span className={`badge ${r.passed ? "ok" : "bad"}`}>{r.score.toFixed(2)}</span>
                    )}
                  </td>
                  <td>
                    {isRegression && (
                      <>
                        <span className="badge regression">回归</span>{" "}
                        <span className="muted">（基线 {delta!.old_score?.toFixed(2)}）</span>
                      </>
                    )}
                    {delta?.change === "improved" && <span className="badge ok">改善</span>}
                    {delta?.change === "new" && <span className="badge">新增</span>}
                    {r.error && <span className="muted">{r.error}</span>}
                  </td>
                  <td>
                    {r.evals
                      .filter((e) => !e.passed)
                      .map((e) => (
                        <div key={e.evaluator}>
                          <span className="mono">[{e.evaluator}]</span> {e.detail}
                          {e.raw && <pre className="detail">{e.raw}</pre>}
                        </div>
                      ))}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </>
  );
}
