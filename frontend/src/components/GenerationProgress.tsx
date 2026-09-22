import type { ExtractDetail, ProgressStage, ProgressState } from "../types";
import { CheckIcon } from "../icons";

const STEPS: { stage: ProgressStage; label: string }[] = [
  { stage: "extract", label: "Извлекаем текст из документов" },
  { stage: "generate", label: "Составляем тест" },
  { stage: "diagrams", label: "Рисуем схемы" },
];

function extractDetailText(d: ExtractDetail): string | null {
  if (!d.filename) return null;
  if (d.total === 0) return d.filename;
  return `${d.filename}: страница ${d.processed} из ${d.total}`;
}

function detailTextOf(progress: ProgressState | null): string | null {
  if (!progress) return null;
  switch (progress.stage) {
    case "extract":
      return extractDetailText(progress.detail);
    case "generate":
      return progress.detail;
    case "diagrams":
      return `${progress.detail.processed} из ${progress.detail.total}`;
  }
}

export default function GenerationProgress({ progress }: { progress: ProgressState | null }) {
  // «Рисуем схемы» — последний этап и приходит только если у теста есть рисунки,
  // поэтому показываем шаг, лишь когда текущий этап — "diagrams".
  const steps = progress?.stage === "diagrams" ? STEPS : STEPS.filter((s) => s.stage !== "diagrams");
  const currentIdx = progress ? steps.findIndex((s) => s.stage === progress.stage) : -1;
  const detailText = detailTextOf(progress);

  return (
    <div className="loading glass1" role="status" aria-live="polite">
      <div className="ring" aria-hidden="true">
        <svg viewBox="0 0 60 60">
          <circle className="ring-bg" cx="30" cy="30" r="26" />
          <circle className="ring-arc" cx="30" cy="30" r="26" />
        </svg>
      </div>
      <p className="loading-t">Генерируем тест…</p>
      <ul className="stages">
        {steps.map((s, i) => {
          const state = i < currentIdx ? "done" : i === currentIdx ? "active" : "";
          return (
            <li key={s.stage} className={`stage ${state}`}>
              <span className="st-ic" aria-hidden="true">
                {state === "done" && <CheckIcon className="ic sm" />}
              </span>
              <span>
                <div>{s.label}</div>
                {state === "active" && detailText && <div className="stage-detail">{detailText}</div>}
              </span>
            </li>
          );
        })}
      </ul>
      <div className="skel" aria-hidden="true">
        <div className="sk o" />
        <div className="sk o" />
      </div>
    </div>
  );
}
