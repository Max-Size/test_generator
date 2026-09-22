import { describe, expect, it, vi } from "vitest";
import { generateQuiz } from "./api";

/** Builds a fetch mock whose `resp.body` streams the given SSE events. */
function mockSseResponse(events: unknown[]) {
  const frames = events.map((e) => `data: ${JSON.stringify(e)}\n\n`).join("");
  const encoder = new TextEncoder();
  const chunk = encoder.encode(frames);
  let sent = false;
  const reader = {
    read: async () => {
      if (sent) return { done: true, value: undefined };
      sent = true;
      return { done: false, value: chunk };
    },
  };
  return {
    ok: true,
    body: { getReader: () => reader },
  };
}

describe("generateQuiz", () => {
  it("posts form data, reports progress events and resolves with the result", async () => {
    const responseBody = { quiz: { questions: [] }, source_chars: 10, truncated: false };
    const fetchMock = vi.fn().mockResolvedValue(
      mockSseResponse([
        { type: "progress", stage: "extract", detail: { filename: "a.pdf", processed: 0, total: 3 } },
        { type: "progress", stage: "generate", detail: null },
        { type: "result", data: responseBody },
      ]),
    );
    vi.stubGlobal("fetch", fetchMock);

    const onProgress = vi.fn();
    const result = await generateQuiz(
      {
        files: [],
        numQuestions: 5,
        questionTypes: ["single"],
        topics: "",
        sourceKinds: ["material"],
      },
      onProgress,
    );

    expect(fetchMock).toHaveBeenCalledWith("/api/generate", expect.objectContaining({ method: "POST" }));
    expect(result).toEqual(responseBody);
    expect(onProgress).toHaveBeenNthCalledWith(1, "extract", { filename: "a.pdf", processed: 0, total: 3 });
    expect(onProgress).toHaveBeenNthCalledWith(2, "generate", null);

    vi.unstubAllGlobals();
  });

  it("forwards diagrams progress events with their detail", async () => {
    const responseBody = { quiz: { questions: [] }, source_chars: 10, truncated: false };
    const fetchMock = vi.fn().mockResolvedValue(
      mockSseResponse([
        { type: "progress", stage: "generate", detail: null },
        { type: "progress", stage: "diagrams", detail: { processed: 0, total: 2 } },
        { type: "progress", stage: "diagrams", detail: { processed: 2, total: 2 } },
        { type: "result", data: responseBody },
      ]),
    );
    vi.stubGlobal("fetch", fetchMock);

    const onProgress = vi.fn();
    const result = await generateQuiz(
      {
        files: [],
        numQuestions: 5,
        questionTypes: ["single"],
        topics: "",
        sourceKinds: ["material"],
      },
      onProgress,
    );

    expect(result).toEqual(responseBody);
    expect(onProgress).toHaveBeenNthCalledWith(2, "diagrams", { processed: 0, total: 2 });
    expect(onProgress).toHaveBeenNthCalledWith(3, "diagrams", { processed: 2, total: 2 });

    vi.unstubAllGlobals();
  });

  it("returns truncated_files when the backend reports truncated/dropped files", async () => {
    const responseBody = {
      quiz: { questions: [] },
      source_chars: 87345,
      truncated: true,
      truncated_files: [
        { filename: "lecture2.pdf", reason: "partial" },
        { filename: "appendix.pdf", reason: "dropped" },
      ],
    };
    const fetchMock = vi.fn().mockResolvedValue(
      mockSseResponse([{ type: "result", data: responseBody }]),
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await generateQuiz(
      {
        files: [],
        numQuestions: 5,
        questionTypes: ["single"],
        topics: "",
        sourceKinds: ["material"],
      },
      () => {},
    );

    expect(result).toEqual(responseBody);

    vi.unstubAllGlobals();
  });

  it("throws with the server-provided detail on a failed (pre-stream) response", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      json: async () => ({ detail: "bad input" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      generateQuiz(
        {
          files: [],
          numQuestions: 5,
          questionTypes: ["single"],
          topics: "",
          sourceKinds: ["material"],
        },
        () => {},
      ),
    ).rejects.toThrow("bad input");

    vi.unstubAllGlobals();
  });

  it("throws with the detail from an in-stream error event", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      mockSseResponse([{ type: "error", status: 502, detail: "LLM недоступна" }]),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      generateQuiz(
        {
          files: [],
          numQuestions: 5,
          questionTypes: ["single"],
          topics: "",
          sourceKinds: ["material"],
        },
        () => {},
      ),
    ).rejects.toThrow("LLM недоступна");

    vi.unstubAllGlobals();
  });
});

describe("generateQuiz numQuestions null", () => {
  it("does not append num_questions", async () => {
    const fetchMock = vi.fn().mockResolvedValue(mockSseResponse([{ type: "result", data: {} }]));
    vi.stubGlobal("fetch", fetchMock);
    await generateQuiz(
      {
        files: [],
        numQuestions: null,
        questionTypes: ["single"],
        topics: "",
        sourceKinds: ["sample"],
      },
      () => {},
    );
    const body = fetchMock.mock.calls[0][1].body as FormData;
    expect(body.has("num_questions")).toBe(false);
    vi.unstubAllGlobals();
  });
});
