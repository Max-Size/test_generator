import type { GenerateResponse } from "./types";

export async function generateQuiz(params: {
  files: File[];
  numQuestions: number;
  questionTypes: string[];
  topics: string;
  sourceMode: string;
}): Promise<GenerateResponse> {
  const fd = new FormData();
  params.files.forEach((f) => fd.append("files", f));
  fd.append("num_questions", String(params.numQuestions));
  fd.append("question_types", params.questionTypes.join(","));
  fd.append("source_mode", params.sourceMode);
  if (params.topics.trim()) fd.append("topics", params.topics.trim());

  const resp = await fetch("/api/generate", { method: "POST", body: fd });
  if (!resp.ok) {
    const detail = await resp.json().catch(() => null);
    throw new Error(detail?.detail ?? `Ошибка ${resp.status}`);
  }
  return resp.json();
}
