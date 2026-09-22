import { useEffect, useMemo, useRef, useState } from "react";
import type { Question, Quiz, TruncatedFile } from "../types";
import RichText from "./RichText";
import QuestionDiagram from "./QuestionDiagram";
import { CheckIcon, InfoIcon, WarnIcon, XIcon } from "../icons";

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
          <div className="prog-r">
            <span>{quiz.title}</span>
            <span>
              Отвечено {answeredCount} из {quiz.questions.length}
            </span>
          </div>
          <div className="bar">
            <div
              className="bar-f"
              style={{ width: `${quiz.questions.length ? (answeredCount / quiz.questions.length) * 100 : 0}%` }}
            />
          </div>
        </div>
      )}

      {mode === "test" && showWarning && truncatedFiles && truncatedFiles.length > 0 && (
        <div className="msg msg-warn section" role="status">
          <span className="msg-ic">
            <WarnIcon />
          </span>
          <div className="msg-b">
            <p className="msg-t">Часть файлов не поместилась полностью</p>
            <ul className="wlist">
              {truncatedFiles.map((f) => (
                <li className="wrow" key={f.filename}>
                  <span className="wname">{f.filename}</span>
                  <span className="wtag">{truncatedReasonText(f)}</span>
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
            <XIcon className="ic sm" />
          </button>
        </div>
      )}

      <div className="qlist">
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
              <div className="q-h">
                <span className="qn">{n + 1}</span>
                <span className="qtype">{QTYPE_LABELS[q.type]}</span>
                {mode === "review" && (
                  <span className={`verdict ${correct ? "ok" : "no"}`}>
                    {correct ? <CheckIcon /> : <XIcon />}
                    {correct ? "Верно" : "Неверно"}
                  </span>
                )}
              </div>

              <p className="q-t">
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
                      {correct ? <CheckIcon className="ic sm" /> : <XIcon className="ic sm" />}
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
                    const showCheck = isPicked;
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
                        <span className={`mk ${q.type === "multiple" ? "c" : "r"}`} aria-hidden="true">
                          {showCheck && <CheckIcon className="ic sm" />}
                        </span>
                        <span className="o-b">
                          <span className="o-t">
                            <RichText>{opt}</RichText>
                          </span>
                          {tag && <span className={`o-tag ${statusClass.trim() === "no" ? "no" : "ok"}`}>{tag}</span>}
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}

              {mode === "review" && (
                <>
                  {q.type === "short" && !correct && (
                    <p className="corr">
                      <CheckIcon className="ic sm" />
                      Верный ответ: <RichText>{q.correct_text ?? ""}</RichText>
                    </p>
                  )}
                  {q.explanation && (
                    <div className="expl">
                      <span className="expl-ic">
                        <InfoIcon />
                      </span>
                      <p className="expl-p">
                        <RichText>{q.explanation}</RichText>
                      </p>
                    </div>
                  )}
                </>
              )}
            </article>
          );
        })}
      </div>

      {mode === "test" && (
        <div className="check-row">
          <button type="button" className="btn btn-primary lg" onClick={handleCheckClick}>
            Проверить
          </button>
          <p className="hint">
            {unconfirmed
              ? `Не отвечено вопросов: ${unansweredQuestions.length}. Нажмите «Проверить» ещё раз, чтобы завершить — они будут засчитаны как неверные.`
              : "Неотвеченные вопросы будут засчитаны как неверные."}
          </p>
        </div>
      )}

      {mode === "review" && (
        <div className="result glass1" ref={resultRef} tabIndex={-1}>
          <div>
            <span className="over">Результат</span>
            <div className="score">
              <span className="sc-n">{score}</span>
              <span className="sc-of">из {quiz.questions.length}</span>
            </div>
            <p className="res-t">{quiz.title}</p>
          </div>
          <div className="dots" aria-hidden="true">
            {quiz.questions.map((q) => {
              const ok = isCorrect(q, answers[q.id]);
              return (
                <span key={q.id} className={`dot ${ok ? "ok" : "no"}`}>
                  {ok ? <CheckIcon className="ic sm" /> : <XIcon className="ic sm" />}
                </span>
              );
            })}
          </div>
          <div className="res-a">
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
