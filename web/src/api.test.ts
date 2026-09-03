import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "./api";

describe("api client", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("prefixes /api and parses json", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify([{ id: 1 }]), { status: 200 }))
    );
    const data = await api<{ id: number }[]>("/projects");
    expect(data[0].id).toBe(1);
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe("/api/projects");
  });

  it("throws detail from error body", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ detail: "suite not found" }), { status: 404 }))
    );
    await expect(api("/suites/9")).rejects.toThrow("suite not found");
  });

  it("returns undefined for 204", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 204 })));
    await expect(api("/projects/1", { method: "DELETE" })).resolves.toBeUndefined();
  });
});
