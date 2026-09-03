import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import SuiteEditorPage from "./SuiteEditorPage";

const SUITE = {
  id: 7,
  project_id: 1,
  name: "s1",
  yaml_text: "name: demo\ntarget: {base_url: http://x, model: m}\ncases:\n  - id: c1\n    input: hi\n",
  updated_at: "2026-09-03T00:00:00",
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/suites/7"]}>
      <Routes>
        <Route path="/suites/:suiteId" element={<SuiteEditorPage />} />
        <Route path="/runs/:runId" element={<div>运行详情页</div>} />
      </Routes>
    </MemoryRouter>
  );
}

function mockFetch(handler: (path: string, init?: RequestInit) => { status?: number; body?: unknown }) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const out = handler(String(input), init) ?? {};
      return new Response(JSON.stringify(out.body ?? null), { status: out.status ?? 200 });
    })
  );
}

describe("SuiteEditorPage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("loads yaml into the editor on mount", async () => {
    mockFetch((path) => {
      if (path === "/api/suites/7") return { body: SUITE };
      if (path.endsWith("/baseline")) return { body: { baseline_run_id: null } };
      return { body: null };
    });
    renderPage();
    await waitFor(() =>
      expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toContain("name: demo")
    );
  });

  it("validate shows parsed case preview", async () => {
    mockFetch((path, init) => {
      if (path === "/api/suites/7") return { body: SUITE };
      if (path.endsWith("/baseline")) return { body: { baseline_run_id: null } };
      if (path.endsWith("/validate"))
        return { body: { ok: true, cases: [{ id: "c1", evaluator_count: 2 }], error: null } };
      return { body: null };
    });
    renderPage();
    await waitFor(() => screen.getByRole("textbox"));
    await userEvent.click(screen.getByRole("button", { name: "校验" }));
    await waitFor(() => expect(screen.getByText("c1")).toBeTruthy());
    expect(screen.getByText("2 个评测器")).toBeTruthy();
  });

  it("shows validation error from server", async () => {
    mockFetch((path) => {
      if (path === "/api/suites/7") return { body: SUITE };
      if (path.endsWith("/baseline")) return { body: { baseline_run_id: null } };
      if (path.endsWith("/validate"))
        return { body: { ok: false, cases: [], error: "Duplicate case ids found" } };
      return { body: null };
    });
    renderPage();
    await waitFor(() => screen.getByRole("textbox"));
    await userEvent.click(screen.getByRole("button", { name: "校验" }));
    await waitFor(() => expect(screen.getByText(/Duplicate case ids/)).toBeTruthy());
  });

  it("run button triggers run and navigates to run detail", async () => {
    mockFetch((path, init) => {
      if (path === "/api/suites/7") return { body: SUITE };
      if (path.endsWith("/baseline")) return { body: { baseline_run_id: null } };
      if (path.endsWith("/runs") && init?.method === "POST") return { status: 202, body: { run_id: 42 } };
      return { body: null };
    });
    renderPage();
    await waitFor(() => screen.getByRole("textbox"));
    await userEvent.click(screen.getByRole("button", { name: "运行" }));
    await waitFor(() => expect(screen.getByText("运行详情页")).toBeTruthy());
  });

  it("shows error box instead of loading spinner when suite load fails", async () => {
    mockFetch((path) => {
      if (path === "/api/suites/7") return { status: 404, body: { detail: "套件不存在" } };
      if (path.endsWith("/baseline")) return { body: { baseline_run_id: null } };
      return { body: null };
    });
    renderPage();
    await waitFor(() => expect(screen.getByText(/加载失败：套件不存在/)).toBeTruthy());
    expect(screen.queryByText("加载中…")).toBeNull();
  });
});
