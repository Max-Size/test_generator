import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import GenerationProgress from "./GenerationProgress";

describe("GenerationProgress", () => {
  it("shows only two steps while no diagrams event has arrived", () => {
    const html = renderToStaticMarkup(
      <GenerationProgress progress={{ stage: "generate", detail: null }} />,
    );
    expect(html).toContain("Составляем тест");
    expect(html).not.toContain("Рисуем схемы");
  });

  it("shows the diagrams step as active with «k из N» detail", () => {
    const html = renderToStaticMarkup(
      <GenerationProgress progress={{ stage: "diagrams", detail: { processed: 1, total: 3 } }} />,
    );
    expect(html).toContain("Рисуем схемы");
    expect(html).toContain("1 из 3");
    expect(html.match(/stage done/g)).toHaveLength(2);
    expect(html).toMatch(/stage active"><span[^>]*><\/span><span><div>Рисуем схемы/);
  });
});
