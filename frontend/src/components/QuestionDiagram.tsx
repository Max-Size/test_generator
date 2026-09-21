import type { Diagram } from "../types";

export default function QuestionDiagram({ diagram }: { diagram: Diagram | null }) {
  if (!diagram) return null;
  return (
    <img
      src={diagram.image_base64}
      alt={diagram.alt_text}
      className="my-2 max-w-full rounded-md border border-slate-200"
    />
  );
}
