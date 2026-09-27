"""Build Word (.docx) versions of the Seed-First documents from their Markdown sources.

    python docs/build/build.py                  # all documents -> docs/build/out/
    python docs/build/build.py act dossier      # selected documents
    python docs/build/build.py --no-word        # skip the Microsoft Word step
    python docs/build/build.py --pdf            # also export PDF previews (needs Word)

Pipeline per document (configs live in docs/build/documents/*.json):

1. build.js    Markdown -> styled .docx (Node + the `docx` package)
2. mathfill.py LaTeX placeholders -> native Word equations (pandoc)
3. Word        fills in the table of contents and saves (Windows with Word only;
               elsewhere the file asks Word to fill it in when first opened)
4. checks      the output is a valid package with no leftover placeholders

One-time setup:  npm ci --prefix docs/build
                 pip install -r docs/build/requirements.txt
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mathfill  # noqa: E402  (sibling module)

DOCUMENTS = HERE / "documents"
W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def word_available() -> bool:
    if sys.platform != "win32" or not shutil.which("powershell"):
        return False
    import winreg

    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Word.Application\CLSID"))
    except OSError:
        return False
    return True


def check(path: Path, *, finalised: bool) -> list[str]:
    """Return a list of problems found in a built .docx (empty when it is sound)."""
    problems = []
    with zipfile.ZipFile(path) as z:
        bad = z.testzip()
        if bad:
            problems.append(f"corrupt zip member {bad}")
        parts = {n: z.read(n).decode("utf-8") for n in z.namelist() if n.endswith(".xml")}
    doc = parts.get("word/document.xml", "")
    try:
        root = ElementTree.fromstring(doc)
    except ElementTree.ParseError as exc:
        return [f"word/document.xml does not parse: {exc}"]
    if "@@MATH" in doc:
        problems.append("unreplaced equation placeholders")
    if any("Â" in xml for xml in parts.values()):
        problems.append("mis-decoded characters (mojibake) found")
    styles = [s.get(f"{W_NS}val") for s in root.iter(f"{W_NS}pStyle")]
    if not any(s in ("Heading1", "Heading2") for s in styles):
        problems.append("no headings found")
    if finalised and "PAGEREF" not in doc:
        problems.append("table of contents was not filled in")
    return problems


def build(config: Path, out_dir: Path, *, use_word: bool, pdf: bool) -> Path:
    name = config.stem
    cfg = json.loads(config.read_text(encoding="utf-8"))
    work = out_dir / ".work"
    work.mkdir(parents=True, exist_ok=True)
    raw, with_math = work / f"{name}.raw.docx", work / f"{name}.math.docx"
    final = out_dir / cfg["fileName"]

    node_args = ["node", str(HERE / "build.js"), str(config), str(raw)]
    if not use_word:
        node_args.append("--update-fields-on-open")
    subprocess.run(node_args, check=True)

    n = mathfill.fill(raw, with_math)
    if n:
        print(f"  inserted {n} equations")

    if use_word:
        ps = [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(HERE / "finalize_word.ps1"),
            "-In",
            str(with_math),
            "-Out",
            str(final),
        ]
        if pdf:
            ps += ["-Pdf", str(final.with_suffix(".pdf"))]
        subprocess.run(ps, check=True)
    else:
        shutil.copyfile(with_math, final)

    problems = check(final, finalised=use_word)
    if problems:
        raise SystemExit(f"{final.name}: " + "; ".join(problems))
    return final


def main(argv: list[str] | None = None) -> None:
    configs = {p.stem: p for p in sorted(DOCUMENTS.glob("*.json"))}
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "names",
        nargs="*",
        metavar="NAME",
        help=f"documents to build (default: all of {', '.join(configs)})",
    )
    parser.add_argument("--out", type=Path, default=HERE / "out", help="output directory")
    word = parser.add_mutually_exclusive_group()
    word.add_argument(
        "--word",
        dest="word",
        action="store_true",
        default=None,
        help="require the Microsoft Word finalise step",
    )
    word.add_argument(
        "--no-word",
        dest="word",
        action="store_false",
        help="skip the Word step (contents page is filled in when opened)",
    )
    parser.add_argument("--pdf", action="store_true", help="also export PDFs (needs Word)")
    args = parser.parse_args(argv)
    unknown = [n for n in args.names if n not in configs]
    if unknown:
        parser.error(f"unknown document(s) {', '.join(unknown)}; choose from {', '.join(configs)}")

    if not shutil.which("node"):
        raise SystemExit("Node.js is required: https://nodejs.org/")
    if not (HERE / "node_modules" / "docx").is_dir():
        raise SystemExit("Node dependencies missing; run: npm ci --prefix docs/build")

    available = word_available()
    use_word = available if args.word is None else args.word
    if use_word and not available:
        raise SystemExit("--word given but Microsoft Word is not available")
    if args.pdf and not use_word:
        raise SystemExit("--pdf needs the Word step")

    args.out.mkdir(parents=True, exist_ok=True)
    for name in args.names or configs:
        print(f"{name}:")
        final = build(configs[name], args.out, use_word=use_word, pdf=args.pdf)
        print(f"  -> {final}")
    if not use_word:
        print(
            "Word step skipped: each document will offer to fill in its contents page when opened."
        )


if __name__ == "__main__":
    main()
