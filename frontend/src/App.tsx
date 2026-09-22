import { useState } from "react";
import { generateQuiz } from "./api";
import UploadForm, { type FormValues } from "./components/UploadForm";
import QuizView from "./components/QuizView";
import GenerationProgress from "./components/GenerationProgress";
import type { GenerateResponse, ProgressState } from "./types";

export default function App() {
  // `submitting` covers the moment between clicking the button and the first
  // `progress` SSE event (so the button disables immediately, as it did with
  // the old boolean `loading`); `progress` drives the step checklist.
  const [submitting, setSubmitting] = useState(false);
  const [progress, setProgress] = useState<ProgressState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GenerateResponse | null>(null);

  const handleSubmit = async (v: FormValues) => {
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      setResult(
        await generateQuiz(v, (stage, detail) =>
          setProgress({ stage, detail } as unknown as ProgressState),
        ),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Неизвестная ошибка");
    } finally {
      setSubmitting(false);
      setProgress(null);
    }
  };

  return (
    <div className="min-h-screen bg-slate-100 py-10">
      <div className="mx-auto max-w-2xl px-4">
        <h1 className="mb-6 text-2xl font-bold text-slate-900">Генератор тестов</h1>

        <UploadForm loading={submitting} onSubmit={handleSubmit} />
        <GenerationProgress progress={progress} />

        {error && (
          <p className="mt-4 rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</p>
        )}

        {result && (
          <div className="mt-8">
            {result.truncated && (
              <ul className="mb-3 rounded-md bg-amber-50 p-3 text-xs text-amber-600">
                {(result.truncated_files ?? []).map((f) => (
                  <li key={f.filename}>
                    {f.filename} —{" "}
                    {f.reason === "partial"
                      ? "обрезан, не поместился целиком"
                      : "не поместился, не включён в тест"}
                  </li>
                ))}
              </ul>
            )}
            <QuizView quiz={result.quiz} />
          </div>
        )}
      </div>
    </div>
  );
}
