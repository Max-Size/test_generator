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
      sourceMode: "auto",
    });

    expect(fetchMock).toHaveBeenCalledWith("/api/generate", expect.objectContaining({ method: "POST" }));
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
        sourceMode: "auto",
      }),
    ).rejects.toThrow("bad input");

    vi.unstubAllGlobals();
  });
});
