import { useEffect, useMemo, useRef, useState } from "react";
import type { Question, Quiz, TruncatedFile } from "../types";
import RichText from "./RichText";
import QuestionDiagram from "./QuestionDiagram";

type Answers = Record<number, number[] | string>;

const QTYPE_LABELS: Record<Question["type"], string> = {
  single: "Один ответ",
  multiple: "Несколько ответов",
  true_false: "Верно / неверно",
  short: "Короткий ответ",
};

function isAnswered(a: number[] | string | undefined): boolean {
  if (a === undefined) return false;
  if (typeof a === "string") return a.trim().length > 0;
  return a.length > 0;
}

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

function truncatedReasonText(f: TruncatedFile): string {
  return f.reason === "partial"
    ? "обрезан, не поместился целиком"
    : "не поместился, не включён в тест";
}

export default function QuizView({
  quiz,
  mode,
  truncatedFiles,
  onCheck,
  onRetake,
  onNewTest,
}: {
  quiz: Quiz;
  mode: "test" | "review";
  truncatedFiles?: TruncatedFile[];
  onCheck: () => void;
  onRetake: () => void;
  onNewTest: () => void;
}) {
  const [answers, setAnswers] = useState<Answers>({});
  const [unconfirmed, setUnconfirmed] = useState(false);
  const [showWarning, setShowWarning] = useState(true);
  const cardRefs = useRef<Map<number, HTMLElement>>(new Map());
  const resultRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (mode === "review") resultRef.current?.focus();
  }, [mode]);

  const setChoice = (q: Question, idx: number) => {
    if (mode !== "test") return;
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

  const unansweredQuestions = useMemo(
    () => quiz.questions.filter((q) => !isAnswered(answers[q.id])),
    [quiz.questions, answers],
  );
  const answeredCount = quiz.questions.length - unansweredQuestions.length;
  const score = useMemo(
    () => quiz.questions.filter((q) => isCorrect(q, answers[q.id])).length,
    [quiz.questions, answers],
  );

  const handleCheckClick = () => {
    if (unansweredQuestions.length > 0 && !unconfirmed) {
      setUnconfirmed(true);
      const first = unansweredQuestions[0];
      const el = cardRefs.current.get(first.id);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        el.focus();
      }
      return;
    }
    setUnconfirmed(false);
    onCheck();
  };

  const lazy = quiz.questions.length > 30;

  return (
    <div>
      {mode === "test" && (
        <div className="prog glass1">
          <span className="prog-label">
            Отвечено {answeredCount} из {quiz.questions.length}
          </span>
          <div className="prog-track">
            <div
              className="prog-fill"
              style={{ width: `${quiz.questions.length ? (answeredCount / quiz.questions.length) * 100 : 0}%` }}
            />
          </div>
        </div>
      )}

      {mode === "test" && showWarning && truncatedFiles && truncatedFiles.length > 0 && (
        <div className="msg msg-warn section" role="status">
          <div>
            <strong>Часть файлов не поместилась полностью:</strong>
            <ul style={{ margin: "6px 0 0", paddingLeft: 18 }}>
              {truncatedFiles.map((f) => (
                <li key={f.filename}>
                  {f.filename} — {truncatedReasonText(f)}
                </li>
              ))}
            </ul>
          </div>
          <button
            type="button"
            className="msg-close"
            aria-label="Закрыть предупреждение"
            onClick={() => setShowWarning(false)}
          >
            ✕
          </button>
        </div>
      )}

      <h2 className="app-title" style={{ fontSize: 20, marginBottom: 16 }}>
        {quiz.title}
      </h2>

      {quiz.questions.map((q, n) => {
        const ans = answers[q.id];
        const picked = q.type === "short" ? [] : ((ans as number[]) ?? []);
        const correct = isCorrect(q, ans);
        const isTf = q.type === "true_false";
        const role = q.type === "multiple" ? "group" : "radiogroup";

        return (
          <article
            key={q.id}
            ref={(el) => {
              if (el) cardRefs.current.set(q.id, el);
              else cardRefs.current.delete(q.id);
            }}
            tabIndex={-1}
            className={`card glass2${lazy ? " card-lazy" : ""}`}
          >
            <div className="card-head">
              <span>
                <span className="qnum">{n + 1}.</span>{" "}
                <span className="qtype">{QTYPE_LABELS[q.type]}</span>
              </span>
              {mode === "review" && (
                <span className={`verdict ${correct ? "ok" : "no"}`}>
                  {correct ? "Верно" : "Неверно"}
                </span>
              )}
            </div>

            <p className="qtext">
              <RichText>{q.text}</RichText>
            </p>

            <QuestionDiagram diagram={q.diagram} />

            {q.type === "short" ? (
              <div className="field-wrap">
                <input
                  type="text"
                  disabled={mode === "review"}
                  value={(ans as string) ?? ""}
                  onChange={(e) => setAnswers((p) => ({ ...p, [q.id]: e.target.value }))}
                  className={
                    "field" + (mode === "review" ? (correct ? " ok" : " no") : "")
                  }
                  placeholder="Ваш ответ"
                  aria-label={`Ответ на вопрос ${n + 1}`}
                />
                {mode === "review" && (
                  <span className={`fstat ${correct ? "ok" : "no"}`} aria-hidden="true">
                    {correct ? "✓" : "✕"}
                  </span>
                )}
              </div>
            ) : (
              <div role={role} className={isTf ? "opts tf" : "opts"} aria-label={`Варианты ответа на вопрос ${n + 1}`}>
                {q.options.map((opt, i) => {
                  const isPicked = picked.includes(i);
                  const isRight = q.correct_indexes.includes(i);
                  let statusClass = "";
                  let tag: string | null = null;
                  if (mode === "review") {
                    if (isPicked && isRight) {
                      statusClass = " ok";
                      tag = "Верно";
                    } else if (isPicked && !isRight) {
                      statusClass = " no";
                      tag = "Неверно";
                    } else if (!isPicked && isRight) {
                      statusClass = " miss";
                      tag = "Пропущено";
                    }
                  }
                  return (
                    <button
                      key={i}
                      type="button"
                      role={q.type === "multiple" ? "checkbox" : "radio"}
                      aria-checked={isPicked}
                      disabled={mode === "review"}
                      className={`opt${statusClass}${mode === "review" ? " locked" : ""}`}
                      onClick={() => setChoice(q, i)}
                    >
                      <span className="opt-mark" aria-hidden="true" />
                      <RichText>{opt}</RichText>
                      {tag && <span className="o-tag">{tag}</span>}
                    </button>
                  );
                })}
              </div>
            )}

            {mode === "review" && (
              <>
                {q.type === "short" && !correct && (
                  <p className="correct-answer">
                    Верный ответ: <strong><RichText>{q.correct_text ?? ""}</RichText></strong>
                  </p>
                )}
                {q.explanation && (
                  <div className="expl inset">
                    <RichText>{q.explanation}</RichText>
                  </div>
                )}
              </>
            )}
          </article>
        );
      })}

      {mode === "test" && (
        <>
          <button type="button" className="btn btn-primary lg" onClick={handleCheckClick}>
            Проверить
          </button>
          <p className="hint">
            {unconfirmed
              ? `Не отвечено вопросов: ${unansweredQuestions.length}. Нажмите «Проверить» ещё раз, чтобы завершить — они будут засчитаны как неверные.`
              : "Неотвеченные вопросы будут засчитаны как неверные."}
          </p>
        </>
      )}

      {mode === "review" && (
        <div className="result glass1" ref={resultRef} tabIndex={-1}>
          <p className="result-score">
            {score} из {quiz.questions.length}
          </p>
          <div className="dots" aria-hidden="true">
            {quiz.questions.map((q) => (
              <span key={q.id} className={`dot ${isCorrect(q, answers[q.id]) ? "ok" : "no"}`} />
            ))}
          </div>
          <div className="result-actions">
            <button type="button" className="btn btn-secondary" onClick={onRetake}>
              Пройти заново
            </button>
            <button type="button" className="btn btn-primary" onClick={onNewTest}>
              Создать новый тест
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
