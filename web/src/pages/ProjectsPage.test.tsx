import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import ProjectsPage from "./ProjectsPage";

function mockFetch(handler: (path: string, init?: RequestInit) => unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const out = handler(String(input), init);
      return new Response(JSON.stringify(out ?? null), {
        status: out instanceof Error ? 422 : 200,
      });
    })
  );
}

describe("ProjectsPage", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("renders project list without interaction", async () => {
    mockFetch(() => [{ id: 1, name: "支付网关", created_at: "2026-09-01" }]);
    render(<MemoryRouter><ProjectsPage /></MemoryRouter>);
    await waitFor(() => expect(screen.getByText("支付网关")).toBeTruthy());
  });

  it("creates a project via the form", async () => {
    const calls: string[] = [];
    mockFetch((path, init) => {
      calls.push(`${init?.method ?? "GET"} ${path}`);
      if (init?.method === "POST") return { id: 2, name: "新项目", created_at: "t" };
      return [{ id: 2, name: "新项目", created_at: "t" }];
    });
    render(<MemoryRouter><ProjectsPage /></MemoryRouter>);
    await userEvent.type(screen.getByPlaceholderText("新项目名称"), "新项目");
    await userEvent.click(screen.getByRole("button", { name: "创建" }));
    await waitFor(() => expect(screen.getByText("新项目")).toBeTruthy());
    expect(calls.some((c) => c.startsWith("POST"))).toBe(true);
  });
});
