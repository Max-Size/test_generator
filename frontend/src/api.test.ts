import { describe, expect, it, vi } from "vitest";
import { generateQuiz } from "./api";

describe("generateQuiz", () => {
  it("posts form data and returns the parsed response", async () => {
    const responseBody = { quiz: { questions: [] }, source_chars: 10, truncated: false };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => responseBody,
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await generateQuiz({
      files: [],
      numQuestions: 5,
      questionTypes: ["single"],
      topics: "",
      sourceKinds: ["material"],
    });

    expect(fetchMock).toHaveBeenCalledWith("/api/generate", expect.objectContaining({ method: "POST" }));
    expect(result).toEqual(responseBody);

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
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => responseBody,
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await generateQuiz({
      files: [],
      numQuestions: 5,
      questionTypes: ["single"],
      topics: "",
      sourceKinds: ["material"],
    });

    expect(result).toEqual(responseBody);

    vi.unstubAllGlobals();
  });

  it("throws with the server-provided detail on a failed response", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      json: async () => ({ detail: "bad input" }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      generateQuiz({
        files: [],
        numQuestions: 5,
        questionTypes: ["single"],
        topics: "",
        sourceKinds: ["material"],
      }),
    ).rejects.toThrow("bad input");

    vi.unstubAllGlobals();
  });
});

describe("generateQuiz numQuestions null", () => {
  it("does not append num_questions", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);
    await generateQuiz({
      files: [],
      numQuestions: null,
      questionTypes: ["single"],
      topics: "",
      sourceKinds: ["sample"],
    });
    const body = fetchMock.mock.calls[0][1].body as FormData;
    expect(body.has("num_questions")).toBe(false);
  });
});
