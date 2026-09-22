import { useState } from "react";
import { generateQuiz } from "./api";
import UploadForm, { type FormValues } from "./components/UploadForm";
import QuizView from "./components/QuizView";
import GenerationProgress from "./components/GenerationProgress";
import type { GenerateResponse, ProgressState } from "./types";
import { WarnIcon, XIcon } from "./icons";

type View = "form" | "loading" | "test" | "review";

export default function App() {
  const [view, setView] = useState<View>("form");
  const [progress, setProgress] = useState<ProgressState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GenerateResponse | null>(null);
  const [attempt, setAttempt] = useState(0);

  const handleSubmit = async (v: FormValues) => {
    setView("loading");
    setError(null);
    setProgress(null);
    try {
      const res = await generateQuiz(v, (stage, detail) =>
        setProgress({ stage, detail } as unknown as ProgressState),
      );
      setResult(res);
      setView("test");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Неизвестная ошибка");
      setView("form");
    } finally {
      setProgress(null);
    }
  };

  const handleRetake = () => {
    setAttempt((a) => a + 1);
    setView("test");
  };

  const handleNewTest = () => {
    setResult(null);
    setView("form");
  };

  return (
    <div className="app">
      <div className="bg-spots" aria-hidden="true">
        <div className="blob b1" />
        <div className="blob b2" />
        <div className="blob b3" />
        <div className="blob b4" />
      </div>
      <h1 className="app-title">Генератор тестов</h1>

      {view === "form" && (
        <>
          {error && (
            <div className="msg msg-err section" role="alert">
              <span className="msg-ic">
                <WarnIcon />
              </span>
              <div className="msg-b">
                <p className="msg-t">Не удалось создать тест</p>
                <p className="msg-p">{error}</p>
              </div>
              <button
                type="button"
                className="msg-close"
                aria-label="Закрыть сообщение об ошибке"
                onClick={() => setError(null)}
              >
                <XIcon className="ic sm" />
              </button>
            </div>
          )}
          <UploadForm loading={false} onSubmit={handleSubmit} />
        </>
      )}

      {view === "loading" && <GenerationProgress progress={progress} />}

      {(view === "test" || view === "review") && result && (
        <QuizView
          key={attempt}
          quiz={result.quiz}
          mode={view}
          truncatedFiles={result.truncated ? result.truncated_files : undefined}
          onCheck={() => setView("review")}
          onRetake={handleRetake}
          onNewTest={handleNewTest}
        />
      )}
    </div>
  );
}
