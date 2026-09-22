import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import QuestionDiagram from "./QuestionDiagram";

const SVG = "data:image/svg+xml;base64,PHN2Zy8+";

describe("QuestionDiagram", () => {
  it("renders the image on a paper figure without figcaption when alt_text is empty", () => {
    const html = renderToStaticMarkup(<QuestionDiagram diagram={{ image_base64: SVG, alt_text: "" }} />);
    expect(html).toContain('<figure class="paper fig">');
    expect(html).toContain(`src="${SVG}"`);
    expect(html).toContain('alt="Рисунок к заданию"');
    expect(html).not.toContain("figcaption");
  });

  it("renders figcaption and alt from a non-empty alt_text", () => {
    const html = renderToStaticMarkup(
      <QuestionDiagram diagram={{ image_base64: SVG, alt_text: "Числовая прямая" }} />,
    );
    expect(html).toContain('alt="Числовая прямая"');
    expect(html).toContain("<figcaption>Числовая прямая</figcaption>");
  });

  it("renders nothing without a diagram", () => {
    expect(renderToStaticMarkup(<QuestionDiagram diagram={null} />)).toBe("");
  });
});
