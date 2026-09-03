import { Link, Route, Routes } from "react-router-dom";

import ProjectsPage from "./pages/ProjectsPage";
import ProjectPage from "./pages/ProjectPage";
import SuiteEditorPage from "./pages/SuiteEditorPage";
import RunsPage from "./pages/RunsPage";
import RunDetailPage from "./pages/RunDetailPage";

export default function App() {
  return (
    <div className="layout">
      <header className="topbar">
        <Link to="/" className="brand">
          llm-regress
        </Link>
        <span className="tagline">LLM 回归测试 · CI for Prompts</span>
      </header>
      <main className="content">
        <Routes>
          <Route path="/" element={<ProjectsPage />} />
          <Route path="/projects/:projectId" element={<ProjectPage />} />
          <Route path="/suites/:suiteId" element={<SuiteEditorPage />} />
          <Route path="/suites/:suiteId/runs" element={<RunsPage />} />
          <Route path="/runs/:runId" element={<RunDetailPage />} />
        </Routes>
      </main>
    </div>
  );
}
