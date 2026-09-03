import { FormEvent, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { api } from "../api";
import type { Suite } from "../types";

export const DEFAULT_SUITE_YAML = `name: my-suite
target:
  provider: openai-compatible
  base_url: https://api.deepseek.com
  api_key_env: DEEPSEEK_API_KEY
  model: deepseek-chat
cases:
  - id: example
    input: "用一句话介绍我们的产品"
    evaluators:
      - type: length
        params: {max_chars: 200}
`;

export default function ProjectPage() {
  const { projectId } = useParams();
  const [suites, setSuites] = useState<Suite[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    api<Suite[]>(`/projects/${projectId}/suites`)
      .then(setSuites)
      .catch((e) => setError(e.message));

  useEffect(() => {
    load();
  }, [projectId]);

  const create = async (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      await api(`/projects/${projectId}/suites`, {
        method: "POST",
        body: JSON.stringify({ name: name.trim(), yaml_text: DEFAULT_SUITE_YAML }),
      });
      setName("");
      setError(null);
      load();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <>
      <h1>用例集</h1>
      {error && <div className="error-box">{error}</div>}
      <form onSubmit={create} className="row" style={{ marginBottom: 24 }}>
        <input
          placeholder="新用例集名称"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <button type="submit">创建</button>
      </form>
      <table>
        <thead>
          <tr><th>名称</th><th>更新时间</th><th></th></tr>
        </thead>
        <tbody>
          {suites.map((s) => (
            <tr key={s.id}>
              <td><Link to={`/suites/${s.id}`}>{s.name}</Link></td>
              <td className="muted mono">{s.updated_at.slice(0, 16).replace("T", " ")}</td>
              <td><Link to={`/suites/${s.id}/runs`}>运行历史</Link></td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
