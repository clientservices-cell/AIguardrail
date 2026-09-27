# Word document build

Generates styled Word (.docx) versions of the Seed-First documents from their Markdown sources in `docs/`. The Markdown files are the source of truth, and the Word files are build outputs.

| Config | Source | Output |
|---|---|---|
| `documents/act.json` | `docs/seed_first_ai_act.md` | `Seed-First_AI_Act_Draft_v2.docx` |
| `documents/framework.json` | `docs/framework.md` | `Seed-First_AI_Governance_Framework_v2.docx` |
| `documents/dossier.json` | `docs/research_dossier.md` | `Seed-First_Research_Dossier.docx` |
| `documents/annex.json` | `docs/regulatory_annex.md` | `Seed-First_Regulatory_Annex.docx` |

## Setup (once)

```bash
npm ci --prefix docs/build
pip install -r docs/build/requirements.txt
```

This needs Node.js 18+ and Python 3.10+. Microsoft Word is optional.

## Build

```bash
python docs/build/build.py
```

Outputs go to `docs/build/out/`, which git ignores. Useful options:

- `python docs/build/build.py act dossier` builds only the named documents.
- `--no-word` skips the Word step.
- `--pdf` also exports PDF previews. This needs Word.

## How it works

1. **`build.js`** (Node, `docx` package) turns the Markdown into a styled document. It adds the title page, contents page, headers and footers, tables, callouts and code panels. Legal paragraph numbers such as `1.` and `(a)` are kept as literal text, so they always match the cross-references.
2. **`mathfill.py`** (pandoc) replaces LaTeX formulas with native, editable Word equations. It also corrects two places where pandoc's output breaks the file-format schema.
3. **`finalize_word.ps1`** (Windows with Word only) fills in the contents page and saves. Without Word, each file instead asks Word to fill in the contents page when it is first opened.
4. **`build.py`** runs the steps above and checks each output. It fails if a file isn't a valid package, if an equation placeholder was left behind, if characters are garbled, or if the contents page is still empty after the Word step.

## Adding or changing a document

Each config sets:

- the source `input` (a path relative to the config file) and the output `fileName`;
- the title-page text: `kicker`, `title`, `subtitle`, `description`, `dateLine`;
- the running `header`;
- an optional `pageBreakBefore` regex, matched against `##` headings;
- `tableWidths`, column widths in twips keyed by each table's first header cell. The widths must sum to at most 9026, the A4 text width;
- `"mathEngine": "pandoc"` for documents with anything beyond a simple formula.

Everything before the first `##` heading is front matter. Its `>` callout becomes the note on the title page.

> **Editing the Word files directly?** Regenerating a document overwrites it. Once a document has moved to Word-based editing, stop building it from Markdown.
