import type { ExtractDetail, ProgressStage, ProgressState } from "../types";
import { CheckIcon } from "../icons";

const STEPS: { stage: ProgressStage; label: string }[] = [
  { stage: "extract", label: "Извлекаем текст из документов" },
  { stage: "generate", label: "Составляем тест" },
];

function extractDetailText(d: ExtractDetail): string | null {
  if (!d.filename) return null;
  if (d.total === 0) return d.filename;
  return `${d.filename}: страница ${d.processed} из ${d.total}`;
}

export default function GenerationProgress({ progress }: { progress: ProgressState | null }) {
  const currentIdx = progress ? STEPS.findIndex((s) => s.stage === progress.stage) : -1;
  const detailText =
    progress?.stage === "extract"
      ? extractDetailText(progress.detail)
      : progress?.stage === "generate"
        ? progress.detail
        : null;

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
        {STEPS.map((s, i) => {
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
