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
  if (!progress) return null;
  const currentIdx = STEPS.findIndex((s) => s.stage === progress.stage);
  const detailText = progress.stage === "extract" ? extractDetailText(progress.detail) : progress.detail;

  return (
    <ul className="mt-4 space-y-1.5 rounded-xl border border-slate-200 bg-white p-4 text-sm shadow-sm">
      {STEPS.map((s, i) => (
        <li key={s.stage} className={i > currentIdx ? "text-slate-400" : "text-slate-900"}>
          <span className="font-medium">
            {i < currentIdx ? "✓ " : i === currentIdx ? "⋯ " : "○ "}
            {s.label}
          </span>
          {i === currentIdx && detailText && (
            <div className="ml-4 text-xs text-slate-500">{detailText}</div>
          )}
        </li>
      ))}
    </ul>
  );
}
