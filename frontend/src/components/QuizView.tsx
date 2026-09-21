import { useState } from "react";
import type { Question, Quiz } from "../types";
import RichText from "./RichText";
import QuestionDiagram from "./QuestionDiagram";

type Answers = Record<number, number[] | string>;

function isCorrect(q: Question, a: number[] | string | undefined): boolean {
  if (a === undefined) return false;
  if (q.type === "short") {
    return (
      typeof a === "string" &&
      a.trim().toLowerCase() === (q.correct_text ?? "").trim().toLowerCase()
    );
  }
  const picked = [...(a as number[])].sort();
  const right = [...q.correct_indexes].sort();
  return picked.length === right.length && picked.every((v, i) => v === right[i]);
}

export default function QuizView({ quiz }: { quiz: Quiz }) {
  const [answers, setAnswers] = useState<Answers>({});
  const [submitted, setSubmitted] = useState(false);

  const setChoice = (q: Question, idx: number) => {
    setAnswers((prev) => {
      if (q.type === "multiple") {
        const cur = (prev[q.id] as number[]) ?? [];
        return {
          ...prev,
          [q.id]: cur.includes(idx) ? cur.filter((i) => i !== idx) : [...cur, idx],
        };
      }
      return { ...prev, [q.id]: [idx] };
    });
  };

  const score = quiz.questions.filter((q) => isCorrect(q, answers[q.id])).length;

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-semibold text-slate-800">{quiz.title}</h2>

      {quiz.questions.map((q, n) => {
        const ans = answers[q.id];
        const ok = isCorrect(q, ans);
        return (
          <div
            key={q.id}
            className={`rounded-xl border bg-white p-5 shadow-sm ${
              submitted ? (ok ? "border-green-400" : "border-red-400") : "border-slate-200"
            }`}
          >
            <p className="font-medium text-slate-800">
              {n + 1}. <RichText>{q.text}</RichText>
            </p>
            <QuestionDiagram diagram={q.diagram} />

            <div className="mt-3 space-y-2">
              {q.type === "short" ? (
                <input
                  type="text"
                  disabled={submitted}
                  value={(ans as string) ?? ""}
                  onChange={(e) => setAnswers((p) => ({ ...p, [q.id]: e.target.value }))}
                  className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                  placeholder="Ваш ответ"
                />
              ) : (
                q.options.map((opt, i) => {
                  const picked = ((ans as number[]) ?? []).includes(i);
                  const right = q.correct_indexes.includes(i);
                  return (
                    <label
                      key={i}
                      className={`flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm ${
                        submitted && right
                          ? "border-green-400 bg-green-50"
                          : submitted && picked && !right
                            ? "border-red-400 bg-red-50"
                            : "border-slate-200"
                      }`}
                    >
                      <input
                        type={q.type === "multiple" ? "checkbox" : "radio"}
                        name={`q-${q.id}`}
                        disabled={submitted}
                        checked={picked}
                        onChange={() => setChoice(q, i)}
                      />
                      <RichText>{opt}</RichText>
                    </label>
                  );
                })
              )}
            </div>

            {submitted && (
              <div className="mt-3 text-sm text-slate-600">
                {q.type === "short" && (
                  <p>
                    Верный ответ:{" "}
                    <span className="font-medium">
                      <RichText>{q.correct_text ?? ""}</RichText>
                    </span>
                  </p>
                )}
                {q.explanation && (
                  <p className="mt-1">
                    <RichText>{q.explanation}</RichText>
                  </p>
                )}
              </div>
            )}
          </div>
        );
      })}

      {submitted ? (
        <div className="rounded-xl bg-indigo-50 p-4 text-center font-semibold text-indigo-800">
          Результат: {score} / {quiz.questions.length}
        </div>
      ) : (
        <button
          onClick={() => setSubmitted(true)}
          className="w-full rounded-md bg-slate-800 px-4 py-2.5 font-medium text-white hover:bg-slate-900"
        >
          Проверить
        </button>
      )}
    </div>
  );
}
