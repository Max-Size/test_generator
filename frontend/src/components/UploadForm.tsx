import { useRef, useState, type CSSProperties } from "react";

const TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: "single", label: "Один ответ" },
  { value: "multiple", label: "Несколько ответов" },
  { value: "true_false", label: "Верно / неверно" },
  { value: "short", label: "Короткий ответ" },
];

const SOURCE_KIND_OPTIONS: { value: string; label: string; desc: string }[] = [
  { value: "material", label: "Теория / конспект", desc: "Тест строится по тексту документа." },
  {
    value: "specification",
    label: "Спецификация / темы экзамена",
    desc: "Тест строится по описанным темам, а не по тексту документа.",
  },
  {
    value: "sample",
    label: "Образец варианта / примеры заданий",
    desc: "Можно определить количество вопросов по образцу.",
  },
];

const ACCEPTED_EXT = [".pdf", ".docx", ".txt", ".md"];

export interface FormValues {
  files: File[];
  numQuestions: number | null;
  questionTypes: string[];
  topics: string;
  sourceKinds: string[];
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} Б`;
  const kb = bytes / 1024;
  if (kb < 1024) return `${kb.toFixed(kb < 10 ? 1 : 0).replace(".", ",")} КБ`;
  const mb = kb / 1024;
  return `${mb.toFixed(mb < 10 ? 1 : 0).replace(".", ",")} МБ`;
}

function extBadge(name: string): string {
  const idx = name.lastIndexOf(".");
  return idx === -1 ? "?" : name.slice(idx + 1).slice(0, 4);
}

function pluralFiles(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 14) return "файлов";
  if (mod10 === 1) return "файл";
  if (mod10 >= 2 && mod10 <= 4) return "файла";
  return "файлов";
}

function pluralQuestions(n: number): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod100 >= 11 && mod100 <= 14) return "вопросов";
  if (mod10 === 1) return "вопрос";
  if (mod10 >= 2 && mod10 <= 4) return "вопроса";
  return "вопросов";
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
  const [autoCount, setAutoCount] = useState(true);
  const [questionTypes, setQuestionTypes] = useState<string[]>(["single", "true_false"]);
  const [topics, setTopics] = useState("");
  const [sourceKinds, setSourceKinds] = useState<string[]>(["material"]);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const addFiles = (list: FileList | null) => {
    if (!list) return;
    setFiles((prev) => [...prev, ...Array.from(list)]);
  };

  const removeFile = (idx: number) => setFiles((prev) => prev.filter((_, i) => i !== idx));

  const toggleKind = (v: string) =>
    setSourceKinds((prev) => (prev.includes(v) ? prev.filter((t) => t !== v) : [...prev, v]));

  const toggleType = (v: string) =>
    setQuestionTypes((prev) => (prev.includes(v) ? prev.filter((t) => t !== v) : [...prev, v]));

  const hasSample = sourceKinds.includes("sample");
  const useAuto = autoCount && hasSample;

  const missing: string[] = [];
  if (files.length === 0) missing.push("файлы");
  if (sourceKinds.length === 0) missing.push("тип документа");
  if (questionTypes.length === 0) missing.push("типы вопросов");

  const canSubmit = missing.length === 0 && !loading;

  return (
    <form
      className="glass1"
      style={{ padding: 28 }}
      onSubmit={(e) => {
        e.preventDefault();
        if (canSubmit) {
          onSubmit({
            files,
            numQuestions: useAuto ? null : numQuestions,
            questionTypes,
            topics,
            sourceKinds,
          });
        }
      }}
    >
      {/* 1. Files */}
      <div className="section">
        <label className="label" id="files-label">
          1. Документы (pdf, docx, txt, md)
        </label>
        <div
          className={`drop${files.length > 0 ? " compact" : ""}${dragOver ? " dragover" : ""}`}
          role="button"
          tabIndex={0}
          aria-labelledby="files-label"
          onClick={() => fileInputRef.current?.click()}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              fileInputRef.current?.click();
            }
          }}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            addFiles(e.dataTransfer.files);
          }}
        >
          <span className="drop-title">
            {files.length > 0 ? "Добавить ещё файлы" : "Перетащите файлы сюда или нажмите, чтобы выбрать"}
          </span>
          {files.length === 0 && <span className="drop-hint">pdf, docx, txt, md</span>}
        </div>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept={ACCEPTED_EXT.join(",")}
          className="sr-only"
          onChange={(e) => {
            addFiles(e.target.files);
            e.target.value = "";
          }}
        />
        {files.length > 0 && (
          <ul className="files">
            {files.map((f, i) => (
              <li className="file" key={`${f.name}-${f.size}-${i}`}>
                <span className="file-badge">{extBadge(f.name)}</span>
                <span className="file-name">{f.name}</span>
                <span className="file-size">{formatSize(f.size)}</span>
                <button
                  type="button"
                  className="iconbtn"
                  aria-label={`Удалить файл ${f.name}`}
                  onClick={() => removeFile(i)}
                >
                  ✕
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* 2. Document type */}
      <div className="section">
        <span className="label">2. Что содержит документ</span>
        <div className="tiles">
          {SOURCE_KIND_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              className="tile"
              aria-pressed={sourceKinds.includes(opt.value)}
              onClick={() => toggleKind(opt.value)}
            >
              <span className="tile-title">{opt.label}</span>
              <span className="tile-desc">{opt.desc}</span>
            </button>
          ))}
        </div>
      </div>

      {/* 3. Question count */}
      <div className="section">
        <span className="label">3. Количество вопросов</span>
        {hasSample && (
          <div className="switch-row" style={{ marginBottom: useAuto ? 0 : 12 }}>
            <button
              type="button"
              role="switch"
              id="auto-count-switch"
              aria-checked={autoCount}
              className="switch"
              onClick={() => setAutoCount((v) => !v)}
            />
            <label htmlFor="auto-count-switch" style={{ cursor: "pointer" }}>
              Определить количество по образцу
            </label>
          </div>
        )}
        {!useAuto && (
          <div className="slider-row" style={{ marginTop: hasSample ? 12 : 0 }}>
            <input
              type="range"
              min={1}
              max={30}
              value={numQuestions}
              className="slider"
              style={{ "--fill": `${((numQuestions - 1) / 29) * 100}%` } as CSSProperties}
              aria-label="Количество вопросов"
              onChange={(e) => setNumQuestions(Number(e.target.value))}
            />
            <span className="slider-value">{numQuestions}</span>
          </div>
        )}
      </div>

      {/* 4. Question types */}
      <div className="section">
        <span className="label">4. Типы вопросов</span>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {TYPE_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              className="chip"
              aria-pressed={questionTypes.includes(opt.value)}
              onClick={() => toggleType(opt.value)}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* 5. Topics */}
      <div className="section">
        <label className="label" htmlFor="topics-input">
          5. Темы для фокуса (необязательно)
        </label>
        <input
          id="topics-input"
          type="text"
          value={topics}
          onChange={(e) => setTopics(e.target.value)}
          placeholder="например: интегралы, теорема Стокса"
          className="field"
        />
      </div>

      <button type="submit" disabled={!canSubmit} className="btn btn-primary lg">
        {loading ? "Генерируем…" : "Создать тест"}
      </button>

      {missing.length > 0 ? (
        <ul className="miss-list">
          {missing.map((m) => (
            <li key={m}>Не хватает: {m}</li>
          ))}
        </ul>
      ) : (
        <p className="ready-summary">
          Всё готово: {files.length} {pluralFiles(files.length)},{" "}
          {useAuto ? "количество вопросов по образцу" : `${numQuestions} ${pluralQuestions(numQuestions)}`}
        </p>
      )}
    </form>
  );
}
