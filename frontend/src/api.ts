import type { GenerateResponse } from "./types";

export async function generateQuiz(
  params: {
    files: File[];
    numQuestions: number | null;
    questionTypes: string[];
    topics: string;
    sourceKinds: string[];
  },
  onProgress: (stage: "extract" | "generate", detail: string | null) => void,
): Promise<GenerateResponse> {
  const fd = new FormData();
  params.files.forEach((f) => fd.append("files", f));
  if (params.numQuestions !== null) fd.append("num_questions", String(params.numQuestions));
  fd.append("question_types", params.questionTypes.join(","));
  fd.append("source_kinds", params.sourceKinds.join(","));
  if (params.topics.trim()) fd.append("topics", params.topics.trim());

  const resp = await fetch("/api/generate", { method: "POST", body: fd });
  if (!resp.ok) {
    // синхронная валидация (422 до открытия потока) — как сегодня
    const detail = await resp.json().catch(() => null);
    throw new Error(detail?.detail ?? `Ошибка ${resp.status}`);
  }

  const reader = resp.body!.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) !== -1) {
      const frame = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      if (!frame.startsWith("data: ")) continue;
      const evt = JSON.parse(frame.slice(6));
      if (evt.type === "progress") onProgress(evt.stage, evt.detail);
      else if (evt.type === "result") return evt.data as GenerateResponse;
      else if (evt.type === "error") throw new Error(evt.detail);
    }
  }
  throw new Error("поток завершился без результата");
}
