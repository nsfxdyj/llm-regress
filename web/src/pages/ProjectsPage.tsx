import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { api } from "../api";
import type { Project } from "../types";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    api<Project[]>("/projects").then(setProjects).catch((e) => setError(e.message));

  useEffect(() => {
    load();
  }, []);

  const create = async (e: FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      await api("/projects", { method: "POST", body: JSON.stringify({ name: name.trim() }) });
      setName("");
      setError(null);
      load();
    } catch (err) {
      setError((err as Error).message);
    }
  };

  return (
    <>
      <h1>项目</h1>
      {error && <div className="error-box">{error}</div>}
      <form onSubmit={create} className="row" style={{ marginBottom: 24 }}>
        <input
          placeholder="新项目名称"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <button type="submit">创建</button>
      </form>
      <table>
        <thead>
          <tr><th>名称</th><th>创建时间</th></tr>
        </thead>
        <tbody>
          {projects.map((p) => (
            <tr key={p.id}>
              <td><Link to={`/projects/${p.id}`}>{p.name}</Link></td>
              <td className="muted mono">{p.created_at.slice(0, 10)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {projects.length === 0 && !error && (
        <p className="muted">还没有项目。创建一个，然后把你的用例集放进来。</p>
      )}
    </>
  );
}
