import type { ExtractDetail, ProgressStage, ProgressState } from "../types";

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
      <div className="skel" aria-hidden="true" />
      <div className="ring" aria-hidden="true" />
      <p className="drop-title">Генерируем тест…</p>
      <ul className="stages">
        {STEPS.map((s, i) => {
          const state = i < currentIdx ? "done" : i === currentIdx ? "active" : "pending";
          return (
            <li key={s.stage} className={`stage ${state}`}>
              <span className="st-ic" aria-hidden="true">
                {state === "done" ? "✓" : ""}
              </span>
              <span>
                <div>{s.label}</div>
                {state === "active" && detailText && <div className="stage-detail">{detailText}</div>}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
