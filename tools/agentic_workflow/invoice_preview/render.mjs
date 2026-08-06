import { createHash } from "node:crypto";
import { createRequire } from "node:module";
import { mkdir, readFile, rm, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";
import { build } from "vite";

const require = createRequire(import.meta.url);
const PLAYWRIGHT_VERSION = require("playwright/package.json").version;
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../..");
const PREVIEW_OUTPUT = path.join(ROOT, "tmp/invoice-preview-validation");
const PDF_OUTPUT = path.join(ROOT, "tmp/invoice-pdf-validation");
const PREVIEW_COMMAND = "node tools/agentic_workflow/invoice_preview/render.mjs";
const PDF_COMMAND = `${PREVIEW_COMMAND} --pdf`;
const PREVIEW_CASES = ["long-label", "both-charts", "single-chart", "no-optional"];
const PDF_CASES = [
  "both-charts",
  "long-label",
  "single-chart",
  "no-optional",
  "multi-project",
  "long-table",
];
const WIDTHS = [
  ["wide", 1120],
  ["narrow", 360],
];
const SOURCES = [
  "src/features/invoices/InvoicePreview.tsx",
  "src/features/invoices/DailyActivityChart.tsx",
  "src/features/invoices/WorkCategoryChart.tsx",
  "src/features/invoices/invoice.css",
  "src/features/invoices/validation-preview/index.html",
  "src/features/invoices/validation-preview/main.tsx",
  "src/features/invoices/validation-preview/documents.ts",
  "src/features/invoices/validation-preview/preview.css",
  "tools/agentic_workflow/invoice_preview/render.mjs",
];

function argument(name) {
  const index = process.argv.indexOf(name);
  return index < 0 ? undefined : process.argv[index + 1];
}

function sha256(data) {
  return createHash("sha256").update(data).digest("hex");
}

async function sourceSha256() {
  const digest = createHash("sha256");
  for (const relativePath of SOURCES) {
    digest.update(relativePath);
    digest.update("\0");
    digest.update(await readFile(path.join(ROOT, relativePath)));
    digest.update("\0");
  }
  return digest.digest("hex");
}

async function validationBundle() {
  const result = await build({
    root: ROOT,
    logLevel: "silent",
    build: {
      cssCodeSplit: false,
      write: false,
      rollupOptions: {
        input: path.join(ROOT, "src/features/invoices/validation-preview/main.tsx"),
        output: {
          format: "iife",
          inlineDynamicImports: true,
          name: "InvoicePreviewValidation",
        },
      },
    },
  });
  const outputs = (Array.isArray(result) ? result : [result]).flatMap(
    (item) => item.output,
  );
  const script = outputs.find((item) => item.type === "chunk" && item.isEntry);
  const stylesheet = outputs.find(
    (item) => item.type === "asset" && item.fileName.endsWith(".css"),
  );
  if (!script || script.type !== "chunk" || !stylesheet || stylesheet.type !== "asset") {
    throw new Error("Vite did not produce one validation script and stylesheet");
  }
  return { script: script.code, stylesheet: String(stylesheet.source) };
}

async function mount(page, bundle, caseName, width) {
  await page.setContent('<main id="root"></main>');
  await page.addStyleTag({ content: bundle.stylesheet });
  await page.evaluate(
    ([configuredCase, configuredWidth]) => {
      window.__INVOICE_PREVIEW_VALIDATION__ = {
        caseName: configuredCase,
        width: configuredWidth,
      };
    },
    [caseName, width],
  );
  await page.addScriptTag({ content: bundle.script });
  await page.locator(".invoice-preview").waitFor();
  await page.evaluate(() => document.fonts.ready);
}

async function previewLayout(page, width) {
  return page.locator(".validation-preview-frame").evaluate((frame, expected) => {
    const preview = frame.querySelector(".invoice-preview");
    const totalDue = [...frame.querySelectorAll("dt")].filter(
      (node) => node.textContent === "Total due",
    );
    if (!(preview instanceof HTMLElement)) throw new Error("Preview is missing");
    const tableLayouts = [...frame.querySelectorAll(".invoice-preview__table-wrap")].map(
      (tableWrap) => {
        if (!(tableWrap instanceof HTMLElement)) {
          throw new Error("Invoice table wrapper is invalid");
        }
        const visibleBounds = tableWrap.getBoundingClientRect();
        const clippedFacts = [
          ...tableWrap.querySelectorAll("tbody td, tbody th, tfoot td, tfoot th"),
        ]
          .filter((node) => {
            const bounds = node.getBoundingClientRect();
            return (
              bounds.left < visibleBounds.left - 1 ||
              bounds.right > visibleBounds.right + 1 ||
              node.scrollWidth > node.clientWidth + 1 ||
              node.scrollHeight > node.clientHeight + 1
            );
          })
          .map((node) => node.textContent?.trim());
        return {
          overflow: tableWrap.scrollWidth - tableWrap.clientWidth,
          clippedFacts,
        };
      },
    );
    const chartLabels = [
      ...frame.querySelectorAll(".invoice-daily-chart__tick, .invoice-daily-chart__date"),
    ].map((node) => {
      if (!(node instanceof SVGGraphicsElement)) {
        throw new Error("Daily chart label is invalid");
      }
      const matrix = node.getScreenCTM();
      const declaredFontSize = Number.parseFloat(window.getComputedStyle(node).fontSize);
      return {
        node,
        text: node.textContent?.trim(),
        effectiveFontSize:
          matrix === null ? 0 : declaredFontSize * Math.hypot(matrix.a, matrix.b),
        bounds: node.getBoundingClientRect(),
      };
    });
    const dateLabels = chartLabels.filter(({ node }) =>
      node.classList.contains("invoice-daily-chart__date"),
    );
    const overlappingDateLabels = dateLabels.flatMap((label, index) =>
      dateLabels.slice(index + 1).flatMap((other) => {
        const overlaps =
          label.bounds.left < other.bounds.right - 1 &&
          label.bounds.right > other.bounds.left + 1 &&
          label.bounds.top < other.bounds.bottom - 1 &&
          label.bounds.bottom > other.bounds.top + 1;
        return overlaps ? [[label.text, other.text]] : [];
      }),
    );
    return {
      frameWidth: Math.round(frame.getBoundingClientRect().width),
      outerOverflow: preview.scrollWidth - preview.clientWidth,
      tableLayouts,
      chartLabelLayout: {
        minimumEffectiveFontSize:
          chartLabels.length === 0
            ? null
            : Math.min(...chartLabels.map(({ effectiveFontSize }) => effectiveFontSize)),
        overlappingDateLabels,
      },
      totalDueCount: totalDue.length,
      figures: frame.querySelectorAll("figure").length,
      expected,
    };
  }, width);
}

async function domEvidence(page) {
  const evidence = await page.evaluate(() => {
    const previews = [...document.querySelectorAll(".invoice-preview")];
    const preview = previews[0];
    if (!(preview instanceof HTMLElement)) throw new Error("Invoice preview is missing");
    const previewBounds = preview.getBoundingClientRect();
    const boundedNodes = [
      ...preview.querySelectorAll(
        "table, th, td, svg, svg text, .invoice-category-chart__label-row, .invoice-preview__total",
      ),
    ];
    const clippedElements = boundedNodes
      .filter((node) => {
        const bounds = node.getBoundingClientRect();
        const horizontallyOutside =
          bounds.left < previewBounds.left - 1 || bounds.right > previewBounds.right + 1;
        const internallyClipped =
          node instanceof HTMLElement &&
          (node.scrollWidth > node.clientWidth + 1 || node.scrollHeight > node.clientHeight + 1);
        return horizontallyOutside || internallyClipped;
      })
      .map((node) => `${node.tagName}:${node.textContent?.trim().slice(0, 80)}`);
    const selectors = [
      ".invoice-daily-chart__guide",
      ".invoice-daily-chart__bar",
      ".invoice-daily-chart__tick",
      ".invoice-daily-chart__date",
      ".invoice-category-chart__track",
      ".invoice-category-chart__fill",
    ];
    const chartStyles = selectors.flatMap((selector) =>
      [...preview.querySelectorAll(selector)].map((node) => {
        const style = getComputedStyle(node);
        return {
          selector,
          fill: style.fill,
          stroke: style.stroke,
          strokeDasharray: style.strokeDasharray,
          fontFamily: style.fontFamily,
          fontSize: style.fontSize,
          backgroundColor: style.backgroundColor,
          borderRadius: style.borderRadius,
          transform: style.transform,
        };
      }),
    );
    const uniqueChartStyles = [
      ...new Map(chartStyles.map((style) => [JSON.stringify(style), style])).values(),
    ];
    return {
      document_count: previews.length,
      text: (preview.textContent ?? "").replace(/\s+/g, " ").trim(),
      figures: preview.querySelectorAll("figure").length,
      printable_bounds: {
        within_horizontal_bounds:
          previewBounds.left >= -1 && previewBounds.right <= window.innerWidth + 1,
        clipped_elements: clippedElements,
      },
      chart_markup: [...preview.querySelectorAll("svg")].map((svg) => svg.outerHTML),
      chart_styles: uniqueChartStyles,
    };
  });
  return {
    ...evidence,
    chart_structure_sha256: sha256(JSON.stringify(evidence.chart_markup)),
    chart_markup: undefined,
  };
}

async function renderPreviews() {
  await rm(PREVIEW_OUTPUT, { recursive: true, force: true });
  await mkdir(PREVIEW_OUTPUT, { recursive: true });
  const bundle = await validationBundle();
  const browser = await chromium.launch({ headless: true });
  const artifacts = [];
  try {
    for (const caseName of PREVIEW_CASES) {
      for (const [label, width] of WIDTHS) {
        const page = await browser.newPage({
          deviceScaleFactor: 1,
          viewport: { width: width + 80, height: 900 },
        });
        await mount(page, bundle, caseName, width);
        const layout = await previewLayout(page, width);
        const expectedFigures =
          caseName === "no-optional" ? 0 : caseName === "single-chart" ? 1 : 2;
        if (
          layout.frameWidth !== width ||
          layout.outerOverflow > 1 ||
          layout.tableLayouts.some(
            (tableLayout) =>
              tableLayout.overflow > 1 || tableLayout.clippedFacts.length > 0,
          ) ||
          (layout.chartLabelLayout.minimumEffectiveFontSize !== null &&
            layout.chartLabelLayout.minimumEffectiveFontSize < 9) ||
          layout.chartLabelLayout.overlappingDateLabels.length > 0 ||
          layout.totalDueCount !== 1 ||
          layout.figures !== expectedFigures
        ) {
          throw new Error(`Invalid ${caseName}/${label} preview layout: ${JSON.stringify(layout)}`);
        }
        const artifactPath = path.join(PREVIEW_OUTPUT, `${caseName}-${label}.png`);
        await page.locator(".validation-preview-frame").screenshot({
          animations: "disabled",
          path: artifactPath,
        });
        const data = await readFile(artifactPath);
        const fileStat = await stat(artifactPath);
        const pngWidth = data.readUInt32BE(16);
        const pngHeight = data.readUInt32BE(20);
        if (pngWidth !== width || pngHeight < 200) {
          throw new Error(`Invalid ${caseName}/${label} screenshot dimensions`);
        }
        artifacts.push({
          case: caseName,
          width: pngWidth,
          height: pngHeight,
          path: artifactPath,
          bytes: fileStat.size,
          sha256: sha256(data),
        });
        await page.close();
      }
    }
    return {
      schema: 1,
      command: PREVIEW_COMMAND,
      renderer: {
        name: "playwright-chromium",
        version: PLAYWRIGHT_VERSION,
        browser_version: browser.version(),
      },
      source_sha256: await sourceSha256(),
      artifacts,
    };
  } finally {
    await browser.close();
  }
}

async function renderPdfs(runToken) {
  if (!runToken) throw new Error("PDF validation requires --run-token");
  await rm(PDF_OUTPUT, { recursive: true, force: true });
  await mkdir(PDF_OUTPUT, { recursive: true });
  const bundle = await validationBundle();
  const browser = await chromium.launch({ headless: true });
  const artifacts = [];
  try {
    for (const caseName of PDF_CASES) {
      const page = await browser.newPage({ viewport: { width: 1200, height: 900 } });
      await mount(page, bundle, caseName, 1120);
      const screen = await domEvidence(page);
      await page.setViewportSize({ width: 794, height: 1123 });
      await page.emulateMedia({ media: "print" });
      await page.evaluate(() =>
        document.documentElement.setAttribute("data-invoice-printing", ""),
      );
      await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(resolve)));
      const printed = await domEvidence(page);
      const artifactPath = path.join(PDF_OUTPUT, `${caseName}.pdf`);
      await page.pdf({
        format: "A4",
        path: artifactPath,
        preferCSSPageSize: true,
        printBackground: true,
        tagged: true,
      });
      const data = await readFile(artifactPath);
      artifacts.push({
        case: caseName,
        pdf: path.relative(ROOT, artifactPath),
        sha256: sha256(data),
        screen,
        print: printed,
      });
      await page.close();
    }
    return {
      schema: 2,
      command: PDF_COMMAND,
      run_token: runToken,
      renderer: {
        name: "playwright-chromium",
        version: PLAYWRIGHT_VERSION,
        browser_version: browser.version(),
      },
      source_sha256: await sourceSha256(),
      artifacts,
    };
  } finally {
    await browser.close();
  }
}

try {
  const result = process.argv.includes("--pdf")
    ? await renderPdfs(argument("--run-token"))
    : await renderPreviews();
  process.stdout.write(`${JSON.stringify(result)}\n`);
} catch (error) {
  process.stderr.write(`${error instanceof Error ? error.stack : String(error)}\n`);
  process.exitCode = 1;
}
