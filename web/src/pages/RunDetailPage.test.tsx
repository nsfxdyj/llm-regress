import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import RunDetailPage from "./RunDetailPage";

const DETAIL = {
  id: 42,
  suite_id: 7,
  status: "done",
  created_at: "2026-09-03T10:00:00",
  finished_at: "2026-09-03T10:00:05",
  summary: { total: 2, passed: 1, errors: 0 },
  error: null,
  judge_changed: false,
  result: {
    results: [
      {
        case_id: "good",
        status: "ok",
        output: "正常输出",
        evals: [{ evaluator: "contains", score: 1, passed: true, detail: "all keywords present", raw: null }],
        score: 1,
        passed: true,
        error: null,
      },
      {
        case_id: "bad",
        status: "ok",
        output: "退化输出",
        evals: [
          {
            evaluator: "judge",
            score: 0.2,
            passed: false,
            detail: "遗漏要点",
            raw: '{"accuracy": 1, "reason": "遗漏要点"}',
          },
        ],
        score: 0.2,
        passed: false,
        error: null,
      },
    ],
  },
  comparison: {
    has_regressions: true,
    has_errors: false,
    summary: "regression: 1, unchanged: 1",
    baseline_run_id: 40,
    deltas: [
      { case_id: "good", old_score: 1, new_score: 1, change: "unchanged" },
      { case_id: "bad", old_score: 0.95, new_score: 0.2, change: "regression" },
    ],
  },
};

function renderPage() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(DETAIL), { status: 200 }))
  );
  return render(
    <MemoryRouter initialEntries={["/runs/42"]}>
      <Routes>
        <Route path="/runs/:runId" element={<RunDetailPage />} />
      </Routes>
    </MemoryRouter>
  );
}

describe("RunDetailPage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("renders case rows with regression highlight", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("bad")).toBeTruthy());
    expect(screen.getByText("回归")).toBeTruthy();
    expect(screen.getByText(/regression: 1/)).toBeTruthy();
    expect(screen.getByText(/基线 0.95/)).toBeTruthy();
  });

  it("shows failing evaluator detail and judge raw", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText("遗漏要点")).toBeTruthy());
    expect(screen.getByText(/accuracy/)).toBeTruthy(); // 裁判原始输出可见
  });

  it("shows promote button for done runs", async () => {
    renderPage();
    await waitFor(() => screen.getByRole("button", { name: "设为基线" }));
  });

  it("shows judge-changed warning instead of comparison", async () => {
    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(JSON.stringify({ ...DETAIL, comparison: null, judge_changed: true }), { status: 200 })
      )
    );
    render(
      <MemoryRouter initialEntries={["/runs/42"]}>
        <Routes>
          <Route path="/runs/:runId" element={<RunDetailPage />} />
        </Routes>
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText(/裁判模型已更换/)).toBeTruthy());
  });

  it("shows error box instead of loading spinner when run load fails", async () => {
    vi.unstubAllGlobals();
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ detail: "运行不存在" }), { status: 404 }))
    );
    render(
      <MemoryRouter initialEntries={["/runs/42"]}>
        <Routes>
          <Route path="/runs/:runId" element={<RunDetailPage />} />
        </Routes>
      </MemoryRouter>
    );
    await waitFor(() => expect(screen.getByText(/加载失败：运行不存在/)).toBeTruthy());
    expect(screen.queryByText("加载中…")).toBeNull();
  });
});
