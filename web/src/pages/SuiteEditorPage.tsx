import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { api } from "../api";
import type { Suite, ValidateResult } from "../types";

export default function SuiteEditorPage() {
  const { suiteId } = useParams();
  const navigate = useNavigate();
  const [suite, setSuite] = useState<Suite | null>(null);
  const [yaml, setYaml] = useState("");
  const [validation, setValidation] = useState<ValidateResult | null>(null);
  const [baselineRunId, setBaselineRunId] = useState<number | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api<Suite>(`/suites/${suiteId}`).then((s) => {
        setSuite(s);
        setYaml(s.yaml_text);
      }),
      api<{ baseline_run_id: number | null }>(`/suites/${suiteId}/baseline`).then((b) =>
        setBaselineRunId(b.baseline_run_id)
      ),
    ]).catch((e) => setLoadError((e as Error).message));
  }, [suiteId]);

  const validate = async () => {
    setBusy(true);
    setMessage(null);
    try {
      await save(); // 先保存再校验，保证校验的是服务端内容
      const v = await api<ValidateResult>(`/suites/${suiteId}/validate`, { method: "POST" });
      setValidation(v);
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const save = async () => {
    if (!suite) return;
    const updated = await api<Suite>(`/suites/${suiteId}`, {
      method: "PUT",
      body: JSON.stringify({ name: suite.name, yaml_text: yaml }),
    });
    setSuite(updated);
  };

  const saveOnly = async () => {
    setBusy(true);
    setMessage(null);
    try {
      await save();
      setMessage("已保存");
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const run = async () => {
    setBusy(true);
    setMessage(null);
    try {
      await save();
      const { run_id } = await api<{ run_id: number }>(`/suites/${suiteId}/runs`, {
        method: "POST",
      });
      navigate(`/runs/${run_id}`);
    } catch (e) {
      setMessage((e as Error).message);
      setBusy(false);
    }
  };

  if (loadError) return <div className="error-box">加载失败：{loadError}</div>;
  if (!suite) return <p className="muted">加载中…</p>;

  return (
    <>
      <h1>{suite.name}</h1>
      <p className="muted">
        基线：{baselineRunId ? `Run #${baselineRunId}` : "未设置（首次运行后可在报告页设为基线）"}
      </p>
      <textarea
        className="yaml-editor"
        value={yaml}
        onChange={(e) => {
          setYaml(e.target.value);
          setValidation(null);
        }}
        spellCheck={false}
      />
      {message && (
        <div className={message === "已保存" ? "notice-box" : "error-box"}>{message}</div>
      )}
      <div className="row" style={{ marginTop: 12 }}>
        <button onClick={run} disabled={busy}>运行</button>
        <button className="ghost" onClick={validate} disabled={busy}>校验</button>
        <button className="ghost" onClick={saveOnly} disabled={busy}>保存</button>
      </div>
      {validation && (
        <>
          <h2>用例预览</h2>
          {validation.ok ? (
            <table>
              <thead>
                <tr><th>用例 ID</th><th>评测器</th></tr>
              </thead>
              <tbody>
                {validation.cases.map((c) => (
                  <tr key={c.id}>
                    <td className="mono">{c.id}</td>
                    <td>{c.evaluator_count} 个评测器</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="error-box">{validation.error}</div>
          )}
        </>
      )}
    </>
  );
}
