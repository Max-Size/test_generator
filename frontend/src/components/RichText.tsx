import { useMemo } from "react";
import katex from "katex";
import "katex/dist/katex.min.css";

// Разбивает строку на текст и формулы и рендерит их через KaTeX. Модель присылает
// LaTeX как в $...$ / $$...$$ (vision-распознавание PDF), так и в \(...\) / \[...\]
// (генерация теста) — поддерживаем оба варианта разделителей.
const TOKEN = /(\$\$[\s\S]+?\$\$|\$[^$\n]+?\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\))/g;

export default function RichText({ children }: { children: string }) {
  const parts = useMemo(() => {
    const text = children ?? "";
    return text.split(TOKEN).map((chunk, i) => {
      const block =
        (chunk.startsWith("$$") && chunk.endsWith("$$")) ||
        (chunk.startsWith("\\[") && chunk.endsWith("\\]"));
      const inline =
        !block &&
        ((chunk.startsWith("$") && chunk.endsWith("$") && chunk.length > 2) ||
          (chunk.startsWith("\\(") && chunk.endsWith("\\)")));
      if (!block && !inline) return { key: i, kind: "text" as const, value: chunk };
      const delimLen = chunk.startsWith("$") ? 1 : 2;
      const tex = chunk.slice(delimLen, chunk.length - delimLen);
      try {
        const html = katex.renderToString(tex, {
          displayMode: block,
          throwOnError: false,
        });
        return { key: i, kind: "math" as const, block, html };
      } catch {
        return { key: i, kind: "text" as const, value: chunk };
      }
    });
  }, [children]);

  return (
    <>
      {parts.map((p) =>
        p.kind === "text" ? (
          <span key={p.key}>{p.value}</span>
        ) : p.block ? (
          <span key={p.key} className="paper fx" dangerouslySetInnerHTML={{ __html: p.html }} />
        ) : (
          <span key={p.key} dangerouslySetInnerHTML={{ __html: p.html }} />
        ),
      )}
    </>
  );
}
