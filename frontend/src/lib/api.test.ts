import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiRequest } from "./api";

afterEach(() => vi.unstubAllGlobals());

describe("API transport", () => {
  it("preserves useful validation feedback from Python", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: "Le motif dépasse le cadre." }), { status: 400 })));
    await expect(apiRequest("/api/convert")).rejects.toMatchObject({ message: "Le motif dépasse le cadre.", status: 400 });
  });

  it("handles a proxy HTML error without leaking parser errors", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<html>too large</html>", { status: 413 })));
    await expect(apiRequest("/api/convert")).rejects.toMatchObject({ message: "Le fichier dépasse la limite de 10 Mio.", status: 413 });
  });

  it("reports an unavailable backend and preserves cancellation", async () => {
    const fetch = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"));
    vi.stubGlobal("fetch", fetch);
    await expect(apiRequest("/api/capabilities")).rejects.toBeInstanceOf(ApiError);
    const aborted = new DOMException("Aborted", "AbortError");
    fetch.mockRejectedValue(aborted);
    await expect(apiRequest("/api/capabilities")).rejects.toBe(aborted);
  });

  it("rejects an invalid success response and leaves multipart encoding to fetch", async () => {
    const fetch = vi.fn().mockResolvedValueOnce(new Response("not JSON", { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ success: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetch);
    await expect(apiRequest("/api/convert")).rejects.toMatchObject({ message: "Réponse inattendue du moteur." });
    const body = new FormData();
    body.set("file", new File(["<svg/>"], "logo.svg"));
    await apiRequest("/api/convert", { method: "POST", body });
    expect(fetch.mock.calls[1][1]).toEqual({ method: "POST", body });
  });
});
