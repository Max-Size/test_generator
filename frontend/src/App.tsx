import { useState } from "react";
import { generateQuiz } from "./api";
import UploadForm, { type FormValues } from "./components/UploadForm";
import QuizView from "./components/QuizView";
import type { GenerateResponse } from "./types";

export default function App() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GenerateResponse | null>(null);

  const handleSubmit = async (v: FormValues) => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await generateQuiz(v));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Неизвестная ошибка");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-100 py-10">
      <div className="mx-auto max-w-2xl px-4">
        <h1 className="mb-6 text-2xl font-bold text-slate-900">Генератор тестов</h1>

        <UploadForm loading={loading} onSubmit={handleSubmit} />

        {error && (
          <p className="mt-4 rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</p>
        )}

        {result && (
          <div className="mt-8">
            {result.analysis &&
              (result.analysis.kinds.includes("specification") ||
                result.analysis.kinds.includes("sample")) && (
                <p className="mb-3 rounded-md bg-indigo-50 p-3 text-xs text-indigo-700">
                  Документ распознан как спецификация экзамена / образец варианта — тест
                  составлен по темам и формату экзамена
                  {result.analysis.topics.length > 0 &&
                    ` (${result.analysis.topics.length} тем)`}
                  .
                </p>
              )}
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
