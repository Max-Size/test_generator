import { useMemo } from "react";
import katex from "katex";
import "katex/dist/katex.min.css";

// Разбивает строку на текст и формулы ($...$ — строчные, $$...$$ — выключные)
// и рендерит формулы через KaTeX. LaTeX приходит из vision-распознавания страниц PDF.
const TOKEN = /(\$\$[\s\S]+?\$\$|\$[^$\n]+?\$)/g;

export default function RichText({ children }: { children: string }) {
  const parts = useMemo(() => {
    const text = children ?? "";
    return text.split(TOKEN).map((chunk, i) => {
      const block = chunk.startsWith("$$") && chunk.endsWith("$$");
      const inline = !block && chunk.startsWith("$") && chunk.endsWith("$") && chunk.length > 2;
      if (!block && !inline) return { key: i, kind: "text" as const, value: chunk };
      const tex = chunk.slice(block ? 2 : 1, block ? -2 : -1);
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
        ) : (
          <span
            key={p.key}
            className={p.block ? "block my-2 overflow-x-auto" : ""}
            dangerouslySetInnerHTML={{ __html: p.html }}
          />
        ),
      )}
    </>
  );
}
