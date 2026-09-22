// E2E-прогон одного файла из test_samples/ через реальный UI (headless Chromium).
// Использование:
//   node e2e/run.mjs --sample ../test_samples/<file> --out <dir> [--base-url http://localhost:5174] [--timeout-s 600]
// Настройки формы берутся из <file без расширения>.e2e.json рядом с файлом (если есть).
// Результат: <out>/result.json + скриншоты. Код выхода 1, если сработала хоть одна автоматическая проверка.
import { chromium } from "playwright";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { parseArgs } from "node:util";

const { values: args } = parseArgs({
  options: {
    sample: { type: "string" },
    out: { type: "string" },
    "base-url": { type: "string", default: "http://localhost:5174" },
    "timeout-s": { type: "string", default: "600" },
  },
});
if (!args.sample || !args.out) {
  console.error("нужны --sample и --out");
  process.exit(2);
}

const samplePath = path.resolve(args.sample);
const outDir = path.resolve(args.out);
mkdirSync(outDir, { recursive: true });
const configPath = samplePath.replace(/\.[^.]+$/, "") + ".e2e.json";
const config = existsSync(configPath) ? JSON.parse(readFileSync(configPath, "utf-8")) : {};
const form = {
  sourceKinds: ["material"],
  questionTypes: ["single", "true_false"],
  autoCount: false,
  numQuestions: 5,
  topics: "",
  ...config.form,
};
const timeoutMs = Number(args["timeout-s"]) * 1000;

const SOURCE_KIND_LABELS = {
  material: "Теория / конспект",
  specification: "Спецификация / темы экзамена",
  sample: "Образец варианта / примеры заданий",
};
const QTYPE_LABELS = {
  single: "Один ответ",
  multiple: "Несколько ответов",
  true_false: "Верно / неверно",
  short: "Короткий ответ",
};

const result = {
  sample: path.basename(samplePath),
  config: configPath && existsSync(configPath) ? path.basename(configPath) : null,
  form,
  expectations: config.expectations ?? [],
  ok: false,
  problems: [],
  generationError: null,
  durationS: null,
  stagesSeen: [],
  quiz: null,
  review: null,
  consoleErrors: [],
  pageErrors: [],
  failedRequests: [],
  screenshots: [],
};
const problem = (msg) => result.problems.push(msg);

async function shot(page, name, fullPage = true) {
  const file = path.join(outDir, `${name}.png`);
  await page.screenshot({ path: file, fullPage });
  result.screenshots.push(file);
}

async function setPressed(page, selector, label, want) {
  const btn = page.locator(selector, { hasText: label });
  if ((await btn.getAttribute("aria-pressed")) !== String(want)) await btn.click();
}

// Анализ отрисованных вопросов: формулы, рисунки, сырой LaTeX.
function inspectCards() {
  const rawLatex = /\\[a-zA-Z]{2,}|\$/;
  const textWithoutMath = (el) => {
    const clone = el.cloneNode(true);
    clone.querySelectorAll(".katex").forEach((k) => k.remove());
    return clone.textContent ?? "";
  };
  // Текст для чтения человеком/агентом: формула → ⟦её TeX-исходник⟧.
  const readable = (el) => {
    if (!el) return null;
    const clone = el.cloneNode(true);
    clone.querySelectorAll(".katex").forEach((k) => {
      const tex = k.querySelector('annotation[encoding="application/x-tex"]')?.textContent ?? "?";
      k.replaceWith(`⟦${tex}⟧`);
    });
    return clone.textContent ?? "";
  };
  return [...document.querySelectorAll("article.card")].map((card, i) => {
    const explanation = card.querySelector(".expl-p");
    return {
      n: i + 1,
      type: card.querySelector(".qtype")?.textContent ?? "",
      text: readable(card.querySelector(".q-t")),
      options: [...card.querySelectorAll(".o-t")].map(readable),
      katexErrors: card.querySelectorAll(".katex-error").length,
      formulas: card.querySelectorAll(".katex").length,
      rawLatexSnippet: (textWithoutMath(card).match(rawLatex) ? textWithoutMath(card).match(/.{0,30}(\\[a-zA-Z]{2,}|\$).{0,30}/)[0] : null),
      explanation: readable(explanation),
      diagrams: [...card.querySelectorAll("figure")].map((f) => {
        const img = f.querySelector("img");
        return {
          figureClass: f.className,
          hasCaption: !!f.querySelector("figcaption"),
          srcPrefix: img?.getAttribute("src")?.slice(0, 30) ?? null,
          loaded: !!img && img.complete && img.naturalWidth > 0,
          naturalWidth: img?.naturalWidth ?? 0,
          naturalHeight: img?.naturalHeight ?? 0,
        };
      }),
    };
  });
}

const t0 = Date.now();
const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  page.on("console", (m) => m.type() === "error" && result.consoleErrors.push(m.text()));
  page.on("pageerror", (e) => result.pageErrors.push(String(e)));
  page.on("requestfailed", (r) => result.failedRequests.push(`${r.method()} ${r.url()} — ${r.failure()?.errorText}`));
  page.on("response", (r) => {
    if (r.url().includes("/api/") && r.status() >= 400) result.failedRequests.push(`${r.status()} ${r.url()}`);
  });

  // 1. Форма
  await page.goto(args["base-url"]);
  await page.locator('input[type="file"]').setInputFiles(samplePath);
  for (const [value, label] of Object.entries(SOURCE_KIND_LABELS)) {
    await setPressed(page, "button.tile", label, form.sourceKinds.includes(value));
  }
  for (const [value, label] of Object.entries(QTYPE_LABELS)) {
    await setPressed(page, "button.chip", label, form.questionTypes.includes(value));
  }
  const autoSwitch = page.locator("#auto-count-switch");
  if (await autoSwitch.count()) {
    if ((await autoSwitch.getAttribute("aria-checked")) !== String(form.autoCount)) await autoSwitch.click();
  }
  if (!(form.autoCount && form.sourceKinds.includes("sample"))) {
    await page.locator('input[type="range"]').fill(String(form.numQuestions));
  }
  if (form.topics) await page.locator("#topics-input").fill(form.topics);
  await shot(page, "01-form");

  // 2. Генерация с наблюдением за прогрессом
  await page.locator('button[type="submit"]').click();
  result.submittedAtS = (Date.now() - t0) / 1000;
  const deadline = Date.now() + timeoutMs;
  let lastStage = null;
  let outcome = null;
  while (Date.now() < deadline) {
    if (await page.locator(".qlist").count()) {
      outcome = "quiz";
      break;
    }
    if (await page.locator(".msg-err").count()) {
      outcome = "error";
      break;
    }
    const active = page.locator(".stage.active");
    if (await active.count()) {
      const label = (await active.locator("div").first().textContent())?.trim() ?? "";
      const detail = (await active.locator(".stage-detail").textContent().catch(() => null)) ?? null;
      const entry = result.stagesSeen.find((s) => s.label === label);
      if (entry) entry.lastDetail = detail;
      else result.stagesSeen.push({ label, firstDetail: detail, lastDetail: detail, atS: (Date.now() - t0) / 1000 });
      if (label !== lastStage) {
        lastStage = label;
        await shot(page, `02-progress-${result.stagesSeen.length}`, false);
      }
    }
    await page.waitForTimeout(250);
  }
  result.durationS = (Date.now() - t0) / 1000;
  result.generationS = result.durationS - result.submittedAtS;

  if (outcome === "error") {
    result.generationError = await page.locator(".msg-err").textContent();
    problem(`генерация завершилась ошибкой: ${result.generationError}`);
    await shot(page, "03-error");
  } else if (outcome === null) {
    problem(`тест не появился за ${args["timeout-s"]} с`);
    await shot(page, "03-timeout");
  } else {
    // 3. Тест
    await page.waitForLoadState("networkidle");
    const cards = await page.evaluate(inspectCards);
    result.quiz = { title: await page.locator(".prog-r span").first().textContent(), questions: cards };
    await shot(page, "03-test");
    if (cards.length === 0) problem("в тесте нет ни одного вопроса");
    for (const c of cards) {
      if (c.katexErrors) problem(`вопрос ${c.n}: ${c.katexErrors} ошибок KaTeX (.katex-error)`);
      if (c.rawLatexSnippet) problem(`вопрос ${c.n}: сырой LaTeX в тексте: «${c.rawLatexSnippet}»`);
      c.diagrams.forEach((d, j) => {
        if (!d.loaded) problem(`вопрос ${c.n}: рисунок ${j + 1} не загрузился`);
      });
    }

    // 4. Ответы и проверка
    for (const card of await page.locator("article.card").all()) {
      const field = card.locator("input.field");
      if (await field.count()) await field.fill("1");
      else await card.locator("button.opt").first().click();
    }
    await page.getByRole("button", { name: "Проверить" }).click();
    if (!(await page.locator(".result").count())) {
      await page.getByRole("button", { name: "Проверить" }).click();
    }
    await page.locator(".result").waitFor({ timeout: 10_000 });
    const reviewCards = await page.evaluate(inspectCards);
    result.review = {
      score: `${await page.locator(".sc-n").textContent()} ${await page.locator(".sc-of").textContent()}`,
      verdicts: await page.locator(".verdict").count(),
      explanations: reviewCards.filter((c) => c.explanation !== null).length,
    };
    await shot(page, "04-review");
    if (result.review.verdicts !== cards.length) {
      problem(`в разборе ${result.review.verdicts} вердиктов на ${cards.length} вопросов`);
    }
    for (const c of reviewCards) {
      if (c.katexErrors) problem(`разбор, вопрос ${c.n}: ${c.katexErrors} ошибок KaTeX`);
      if (c.rawLatexSnippet) problem(`разбор, вопрос ${c.n}: сырой LaTeX: «${c.rawLatexSnippet}»`);
    }
  }
  if (result.consoleErrors.length) problem(`ошибки в консоли браузера: ${result.consoleErrors.length}`);
  if (result.pageErrors.length) problem(`необработанные JS-исключения: ${result.pageErrors.length}`);
  if (result.failedRequests.length) problem(`упавшие запросы: ${result.failedRequests.length}`);
} catch (e) {
  problem(`сценарий упал: ${e instanceof Error ? e.message : String(e)}`);
} finally {
  await browser.close();
}

result.ok = result.problems.length === 0;
writeFileSync(path.join(outDir, "result.json"), JSON.stringify(result, null, 2));
console.log(JSON.stringify({ ok: result.ok, problems: result.problems, durationS: result.durationS, out: outDir }, null, 2));
process.exit(result.ok ? 0 : 1);
