import { useState } from "react";

const TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: "single", label: "Один ответ" },
  { value: "multiple", label: "Несколько ответов" },
  { value: "true_false", label: "Верно / неверно" },
  { value: "short", label: "Короткий ответ" },
];

const SOURCE_MODE_OPTIONS: { value: string; label: string }[] = [
  { value: "auto", label: "Определить автоматически" },
  { value: "material", label: "Теория / конспект" },
  { value: "specification", label: "Спецификация экзамена / образец варианта" },
];

export interface FormValues {
  files: File[];
  numQuestions: number;
  questionTypes: string[];
  topics: string;
  sourceMode: string;
}

export default function UploadForm({
  loading,
  onSubmit,
}: {
  loading: boolean;
  onSubmit: (v: FormValues) => void;
}) {
  const [files, setFiles] = useState<File[]>([]);
  const [numQuestions, setNumQuestions] = useState(10);
  const [questionTypes, setQuestionTypes] = useState<string[]>(["single", "true_false"]);
  const [topics, setTopics] = useState("");
  const [sourceMode, setSourceMode] = useState("auto");

  const toggleType = (v: string) =>
    setQuestionTypes((prev) =>
      prev.includes(v) ? prev.filter((t) => t !== v) : [...prev, v],
    );

  const canSubmit = files.length > 0 && questionTypes.length > 0 && !loading;

  return (
    <form
      className="space-y-5 rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
      onSubmit={(e) => {
        e.preventDefault();
        if (canSubmit) onSubmit({ files, numQuestions, questionTypes, topics, sourceMode });
      }}
    >
      <div>
        <label className="mb-1 block text-sm font-medium text-slate-700">
          Документы (pdf, docx, txt, md)
        </label>
        <input
          type="file"
          multiple
          accept=".pdf,.docx,.txt,.md"
          onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
          className="block w-full text-sm text-slate-600 file:mr-3 file:rounded-md file:border-0 file:bg-slate-100 file:px-3 file:py-2 file:text-sm file:font-medium hover:file:bg-slate-200"
        />
        {files.length > 0 && (
          <p className="mt-1 text-xs text-slate-500">
            {files.map((f) => f.name).join(", ")}
          </p>
        )}
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium text-slate-700">
          Что за документ
        </label>
        <select
          value={sourceMode}
          onChange={(e) => setSourceMode(e.target.value)}
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
        >
          {SOURCE_MODE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <p className="mt-1 text-xs text-slate-500">
          Для спецификации экзамена тест строится по описанным темам и образцу варианта,
          а не по тексту документа.
        </p>
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium text-slate-700">
          Количество вопросов: {numQuestions}
        </label>
        <input
          type="range"
          min={1}
          max={30}
          value={numQuestions}
          onChange={(e) => setNumQuestions(Number(e.target.value))}
          className="w-full"
        />
      </div>

      <div>
        <span className="mb-1 block text-sm font-medium text-slate-700">Типы вопросов</span>
        <div className="flex flex-wrap gap-2">
          {TYPE_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => toggleType(opt.value)}
              className={`rounded-full border px-3 py-1 text-sm ${
                questionTypes.includes(opt.value)
                  ? "border-indigo-600 bg-indigo-600 text-white"
                  : "border-slate-300 bg-white text-slate-700"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="mb-1 block text-sm font-medium text-slate-700">
          Темы для фокуса (необязательно)
        </label>
        <input
          type="text"
          value={topics}
          onChange={(e) => setTopics(e.target.value)}
          placeholder="например: интегралы, теорема Стокса"
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
        />
      </div>

      <button
        type="submit"
        disabled={!canSubmit}
        className="w-full rounded-md bg-indigo-600 px-4 py-2.5 font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
      >
        {loading ? "Генерируем…" : "Создать тест"}
      </button>
    </form>
  );
}
