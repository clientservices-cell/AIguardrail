// Build a styled Word document from one of the repo's Markdown docs.
//
// Usage: node build.js <documents/NAME.json> <out.docx> [--update-fields-on-open]
//
// Normally run through build.py, which also inserts equations (mathfill.py) and
// finalises the document in Word. Supports the Markdown subset the docs use:
//   ## / ### headings; paragraphs; > callouts; | tables |; ``` fenced code;
//   "1." and "- (a)" legal paragraphs (numbering kept as literal text so it matches
//   cross-references); "-" bullets (two levels); $$ display $$ and $inline$ LaTeX;
//   **bold** (may contain *italic*), *italic*, `code`, [links] (text kept, URL dropped).
// Everything before the first "##" heading is front matter: the title page comes
// from the config, plus any > callout found there.
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, Table, TableRow,
  TableCell, WidthType, ShadingType, BorderStyle, Header, Footer, PageNumber,
  TableOfContents, PageBreak, LevelFormat, TabStopType, TableLayoutType,
  Math: OMath, MathRun, MathSubScript, MathFunction, MathRoundBrackets,
} = require("docx");

const [configPath, outputPath] = process.argv.slice(2, 4);
if (!configPath || !outputPath) {
  console.error("usage: node build.js <config.json> <out.docx> [--update-fields-on-open]");
  process.exit(2);
}
const updateFieldsOnOpen = process.argv.includes("--update-fields-on-open");
const cfg = JSON.parse(fs.readFileSync(configPath, "utf8"));
const inputPath = path.resolve(path.dirname(configPath), cfg.input); // relative to the config
const md = fs.readFileSync(inputPath, "utf8").replace(/\r\n/g, "\n");

// ---- palette & metrics --------------------------------------------------------
const NAVY = "1F3864", ACCENT = "2E75B6", MUTED = "595959", RULE = "BFBFBF";
const BODY_FONT = "Cambria", HEAD_FONT = "Calibri", MONO = "Consolas";
const PAGE_W = 11906, PAGE_H = 16838, MARGIN = 1440;           // A4, 1" margins
const CONTENT_W = PAGE_W - 2 * MARGIN;                           // 9026 DXA
const STEP = 567;                                                // 1 cm indent step

// ---- LaTeX (the small subset the docs use) -> Word equation ---------------------
function latexToMath(src) {
  // Supports \text{..}, subscripts _x / _{..}, \min( .. ), \big( \big), \; \, spacing.
  const s = src.replace(/\\big([()])/g, "$1").replace(/\\[;,!]/g, " ").trim();
  let i = 0;
  const readGroup = () => {                       // after '{'
    let depth = 1, start = i;
    while (i < s.length && depth) { if (s[i] === "{") depth++; else if (s[i] === "}") depth--; i++; }
    return s.slice(start, i - 1);
  };
  const plain = (t) => t.replace(/\\text\{([^}]*)\}/g, "$1").replace(/[{}]/g, "");
  function parse(stopAt) {
    const out = [];
    while (i < s.length && s[i] !== stopAt) {
      if (s.startsWith("\\min", i) || s.startsWith("\\max", i)) {
        const name = s.slice(i + 1, i + 4); i += 4;
        while (s[i] === " ") i++;
        if (s[i] === "(") { i++; const inner = parse(")"); i++;
          out.push(new MathFunction({ name: [new MathRun(name)], children: [new MathRoundBrackets({ children: inner })] }));
        } else out.push(new MathRun(name));
        continue;
      }
      let base;
      if (s.startsWith("\\text{", i)) { i += 6; base = plain(readGroup()); }
      else if (/[A-Za-z]/.test(s[i])) { let j = i; while (j < s.length && /[A-Za-z]/.test(s[j])) j++; base = s.slice(i, j); i = j; }
      else { base = s[i] === " " ? "" : s[i]; i++; if (!base) continue; }
      if (s[i] === "_") {
        i++;
        let sub;
        if (s[i] === "{") { i++; sub = plain(readGroup()); } else { sub = s[i]; i++; }
        out.push(new MathSubScript({ children: [new MathRun(base)], subScript: [new MathRun(sub)] }));
      } else out.push(new MathRun(base === "," ? ", " : base === "=" ? " = " : base));
    }
    return out;
  }
  return new OMath({ children: parse(null) });
}
const PANDOC = cfg.mathEngine === "pandoc";
const formulas = [];                                   // [{latex, display}] for mathfill.py
const mathPlaceholder = (latex, display) => {
  formulas.push({ latex: latex.trim(), display });
  return `@@MATH${formulas.length - 1}@@`;
};
const inlineLatex = (t) => t.replace(/\\cdot/g, "·").replace(/\\text\{([^}]*)\}/g, "$1").replace(/[{}\\]/g, "");

// ---- inline markdown -> runs ---------------------------------------------------
function runs(text, base = {}) {
  const out = [];
  const re = /(\*\*(?:[^*]|\*[^*]+\*)+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\)|\$[^$]+\$|\*[^*\s][^*]*\*)/g;
  let last = 0, m;
  const push = (t, extra = {}) => t && out.push(new TextRun({ text: t, ...base, ...extra }));
  while ((m = re.exec(text))) {
    push(text.slice(last, m.index));
    const tok = m[0];
    if (tok.startsWith("**")) out.push(...runs(tok.slice(2, -2), { ...base, bold: true }));
    else if (tok.startsWith("`"))
      push(tok.slice(1, -1), { font: MONO, size: Math.max((base.size || 21) - 2, 16) });
    else if (tok.startsWith("[")) out.push(...runs(tok.match(/^\[([^\]]+)\]/)[1], base));   // keep text, drop repo-relative link
    else if (tok.startsWith("$"))
      PANDOC ? push(mathPlaceholder(tok.slice(1, -1), false))
             : push(inlineLatex(tok.slice(1, -1)), { italics: true, font: "Cambria Math" });
    else out.push(...runs(tok.slice(1, -1), { ...base, italics: true }));
    last = m.index + tok.length;
  }
  push(text.slice(last));
  return out;
}

// ---- block builders --------------------------------------------------------------
const para = (text, opts = {}) =>
  new Paragraph({ children: runs(text, opts.run || {}), spacing: { after: 120 }, ...opts.p });

function labelled(label, text, level) {
  // Literal label ("1." / "(a)") with a hanging indent, so numbering matches references.
  const left = STEP * (level + 1);
  return new Paragraph({
    children: [new TextRun({ text: label }), new TextRun({ text: "\t" }), ...runs(text)],
    indent: { left, hanging: STEP },
    tabStops: [{ type: TabStopType.LEFT, position: left }],
    spacing: { after: 100 },
  });
}

const bullet = (text, level) =>
  new Paragraph({ children: runs(text), numbering: { reference: "bullets", level }, spacing: { after: 80 } });

function callout(paragraphs) {
  return paragraphs.map((t, i) => new Paragraph({
    children: runs(t, { size: 19, color: "262626" }),
    shading: { type: ShadingType.CLEAR, fill: "EEF3FA", color: "auto" },
    border: { left: { style: BorderStyle.SINGLE, size: 18, color: ACCENT, space: 8 } },
    indent: { left: 180, right: 180 },
    spacing: { before: i === 0 ? 120 : 0, after: i === paragraphs.length - 1 ? 240 : 100 },
  }));
}

function table(rows) {
  const cells = rows.map((r) => r.replace(/^\||\|$/g, "").split("|").map((c) => c.trim()));
  const header = cells[0], body = cells.slice(2);
  const n = header.length;
  const widths = (cfg.tableWidths || {})[header[0]] || Array(n).fill(Math.floor(CONTENT_W / n));
  if (widths.length !== n || widths.reduce((a, b) => a + b, 0) > CONTENT_W)
    throw new Error(`bad widths for table "${header[0]}": ${widths}`);
  const border = { style: BorderStyle.SINGLE, size: 4, color: RULE };
  const borders = { top: border, bottom: border, left: border, right: border };
  const mk = (text, i, isHead, stripe) => new TableCell({
    width: { size: widths[i], type: WidthType.DXA },
    borders,
    shading: { type: ShadingType.CLEAR, color: "auto", fill: isHead ? NAVY : stripe ? "F2F5FA" : "FFFFFF" },
    margins: { top: 60, bottom: 60, left: 100, right: 100 },
    children: [new Paragraph({
      // Zero-width break points after "/" let long code paths wrap at directory boundaries.
      children: runs(text.replace(/`[^`]+`/g, (c) => c.replace(/\//g, "/\u200b")),
                     isHead ? { bold: true, color: "FFFFFF", size: 18, font: HEAD_FONT }
                                  : { size: 17 }),
      spacing: { after: 0 },
    })],
  });
  return new Table({
    width: { size: widths.reduce((a, b) => a + b, 0), type: WidthType.DXA },
    columnWidths: widths,
    layout: TableLayoutType.FIXED,
    rows: [
      new TableRow({ tableHeader: true, cantSplit: true, children: header.map((h, i) => mk(h, i, true)) }),
      ...body.map((r, ri) => new TableRow({ cantSplit: true, children: r.map((c, i) => mk(c, i, false, ri % 2 === 1)) })),
    ],
  });
}

// ---- parse the markdown body ------------------------------------------------------
const lines = md.split("\n");
const firstSection = lines.findIndex((l) => l.startsWith("## "));
const statusQuote = [];
{
  let cur = [];
  for (const l of lines.slice(0, firstSection).filter((l) => l.startsWith(">"))) {
    const t = l.replace(/^>\s?/, "");
    if (!t.trim()) { if (cur.length) statusQuote.push(cur.join(" ")); cur = []; } else cur.push(t);
  }
  if (cur.length) statusQuote.push(cur.join(" "));
}

const breakBefore = new RegExp(cfg.pageBreakBefore || "^$a");
const body = [];
let i = firstSection, paraBuf = [];
const flush = () => { if (paraBuf.length) { body.push(para(paraBuf.join(" "))); paraBuf = []; } };
const listRe = /^(\s*)(\d+\.|-)\s+(.*)$/;

while (i < lines.length) {
  const line = lines[i];
  if (!line.trim()) { flush(); i++; continue; }
  if (line.trim() === "---") { flush(); i++; continue; }

  if (line.startsWith("```")) {
    // Fenced code: verbatim, monospace, shaded panel; one paragraph per line.
    flush();
    const code = [];
    i++;
    while (i < lines.length && !lines[i].startsWith("```")) code.push(lines[i++]);
    i++;
    const border = { style: BorderStyle.SINGLE, size: 18, color: "8EA9C8", space: 8 };
    code.forEach((c, k) => body.push(new Paragraph({
      children: [new TextRun({ text: c || " ", font: MONO, size: 18, color: "1F1F1F" })],
      shading: { type: ShadingType.CLEAR, fill: "F3F4F6", color: "auto" },
      border: { left: border },
      indent: { left: 180, right: 180 },
      spacing: { before: k === 0 ? 120 : 0, after: k === code.length - 1 ? 200 : 0, line: 240 },
      keepNext: k < code.length - 1,
    })));
    continue;
  }
  if (line.trim() === "$$") {
    flush();
    const src = [];
    i++;
    while (i < lines.length && lines[i].trim() !== "$$") src.push(lines[i++]);
    i++;
    body.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 160, after: 200 },
                              children: [PANDOC ? new TextRun(mathPlaceholder(src.join("\n"), true))
                                                : latexToMath(src.join(" "))] }));
    continue;
  }
  if (line.startsWith("## ")) {
    flush();
    const text = line.slice(3).trim();
    if (breakBefore.test(text)) body.push(new Paragraph({ children: [new PageBreak()] }));
    body.push(new Paragraph({ heading: HeadingLevel.HEADING_1, children: runs(text) }));
    i++; continue;
  }
  if (line.startsWith("### ")) {
    flush();
    body.push(new Paragraph({ heading: HeadingLevel.HEADING_2, children: runs(line.slice(4).trim()) }));
    i++; continue;
  }
  if (line.startsWith(">")) {
    flush();
    const ps = []; let cur = [];
    while (i < lines.length && lines[i].startsWith(">")) {
      const t = lines[i].replace(/^>\s?/, "");
      if (!t.trim()) { if (cur.length) ps.push(cur.join(" ")); cur = []; } else cur.push(t);
      i++;
    }
    if (cur.length) ps.push(cur.join(" "));
    body.push(...callout(ps));
    continue;
  }
  if (line.startsWith("|")) {
    flush();
    const rows = [];
    while (i < lines.length && lines[i].startsWith("|")) rows.push(lines[i++]);
    body.push(table(rows), new Paragraph({ children: [], spacing: { after: 120 } }));
    continue;
  }
  const m = line.match(listRe);
  if (m) {
    flush();
    const level = m[1].length >= 2 ? 1 : 0;
    const [, , marker, rest] = m;
    const letter = rest.match(/^(\([a-z]+\))\s+(.*)$/);
    if (marker !== "-") body.push(labelled(marker, rest, level));
    else if (letter) body.push(labelled(letter[1], letter[2], level));
    else body.push(bullet(rest, level));
    i++; continue;
  }
  if (/^\s{2,}\S/.test(line) && !paraBuf.length) {
    body.push(new Paragraph({ children: runs(line.trim()), indent: { left: STEP }, spacing: { after: 100 } }));
    i++; continue;
  }
  paraBuf.push(line.trim());
  i++;
}
flush();

// ---- title page ------------------------------------------------------------------
const titlePage = [
  new Paragraph({ spacing: { before: 2400 }, children: [] }),
  new Paragraph({
    children: [new TextRun({ text: cfg.kicker, font: HEAD_FONT, size: 20, bold: true, color: ACCENT, characterSpacing: 40 })],
    spacing: { after: 240 },
  }),
  new Paragraph({
    children: [new TextRun({ text: cfg.title, font: HEAD_FONT, size: 64, bold: true, color: NAVY })],
    spacing: { after: 200 },
  }),
  new Paragraph({
    children: [new TextRun({ text: cfg.subtitle, font: HEAD_FONT, size: 30, color: MUTED })],
    spacing: { after: 360 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: ACCENT, space: 12 } },
  }),
  new Paragraph({ children: runs(cfg.description, { italics: true, color: MUTED }), spacing: { after: 480 } }),
  ...callout(statusQuote),
  new Paragraph({
    children: [new TextRun({ text: cfg.dateLine, font: HEAD_FONT, size: 20, color: MUTED })],
    spacing: { before: 600 },
  }),
  new Paragraph({ children: [new PageBreak()] }),
  new Paragraph({
    children: [new TextRun({ text: "Contents", font: HEAD_FONT, size: 32, bold: true, color: NAVY })],
    spacing: { after: 200 },
  }),
  new TableOfContents("Contents", { hyperlink: true, headingStyleRange: "1-2" }),
  new Paragraph({ children: [new PageBreak()] }),
];

// ---- document ---------------------------------------------------------------------
const doc = new Document({
  creator: "Seed-First AI Guardrail project",
  // Without the Word finalise step the contents page is an unfilled field;
  // this makes Word offer to fill it in when the file is opened.
  features: { updateFields: updateFieldsOnOpen },
  title: cfg.docTitle,
  description: cfg.docDescription,
  styles: {
    default: { document: { run: { font: BODY_FONT, size: 21 }, paragraph: { spacing: { line: 276 } } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: HEAD_FONT, size: 30, bold: true, color: NAVY },
        paragraph: { spacing: { before: 360, after: 160 }, keepNext: true, keepLines: true, outlineLevel: 0,
                     border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: RULE, space: 4 } } } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: HEAD_FONT, size: 24, bold: true, color: NAVY },
        paragraph: { spacing: { before: 280, after: 100 }, keepNext: true, keepLines: true, outlineLevel: 1 } },
    ],
  },
  numbering: {
    config: [{
      reference: "bullets",
      levels: [0, 1].map((level) => ({
        level, format: LevelFormat.BULLET, text: level ? "–" : "•", alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: STEP * (level + 1), hanging: 360 } } },
      })),
    }],
  },
  sections: [{
    properties: {
      titlePage: true,
      page: { size: { width: PAGE_W, height: PAGE_H }, margin: { top: MARGIN, bottom: MARGIN, left: MARGIN, right: MARGIN } },
    },
    headers: {
      first: new Header({ children: [new Paragraph({ children: [] })] }),
      default: new Header({ children: [new Paragraph({
        alignment: AlignmentType.RIGHT,
        children: [new TextRun({ text: cfg.header, font: HEAD_FONT, size: 16, color: MUTED })],
      })] }),
    },
    footers: {
      first: new Footer({ children: [new Paragraph({ children: [] })] }),
      default: new Footer({ children: [new Paragraph({
        alignment: AlignmentType.CENTER,
        children: [new TextRun({ children: ["Page ", PageNumber.CURRENT, " of ", PageNumber.TOTAL_PAGES], font: HEAD_FONT, size: 16, color: MUTED })],
      })] }),
    },
    children: [...titlePage, ...body],
  }],
});

// Multi-letter names in equations (\text{..}, \min) are set upright, as in LaTeX.
async function uprightMathWords(buf) {
  const zip = await require("jszip").loadAsync(buf);
  const xml = await zip.file("word/document.xml").async("string");
  const fixed = xml.replace(/<m:r>((?:(?!<\/m:r>).)*?<m:t[^>]*>([^<]*)<\/m:t>)/g, (all, inner, text) =>
    /^[A-Za-z]{2,}$/.test(text) ? `<m:r><m:rPr><m:sty m:val="p"/></m:rPr>${inner}` : all);
  zip.file("word/document.xml", fixed);
  return zip.generateAsync({ type: "nodebuffer", compression: "DEFLATE" });
}

Packer.toBuffer(doc).then(uprightMathWords).then((buf) => {
  fs.writeFileSync(outputPath, buf);
  // Always written (possibly empty) so build.py can treat every document the same way.
  fs.writeFileSync(outputPath + ".math.json", JSON.stringify(formulas, null, 2));
  console.log(`wrote ${outputPath} (${buf.length} bytes, ${body.length} blocks, ${formulas.length} formulas)`);
});
