import type { Diagram } from "../types";

export default function QuestionDiagram({ diagram }: { diagram: Diagram | null }) {
  if (!diagram) return null;
  return (
    <figure className="paper fig">
      <img src={diagram.image_base64} alt={diagram.alt_text} />
      <figcaption>{diagram.alt_text}</figcaption>
    </figure>
  );
}
