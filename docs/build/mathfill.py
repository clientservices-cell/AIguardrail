"""Replace @@MATHn@@ placeholders in a .docx with native Word equations.

build.js leaves a placeholder run wherever a LaTeX formula appears and writes the
formulas to ``<in.docx>.math.json``. This script renders all of them in one pandoc
call (texmath LaTeX -> OMML) and swaps each placeholder for its equation.

Usage: python mathfill.py in.docx out.docx
"""

from __future__ import annotations

import copy
import json
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

from lxml import etree

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
PLACEHOLDER = re.compile(r"@@MATH(\d+)@@")
ZERO_WIDTH_SPACE = "\u200b"


def w(tag: str) -> str:
    return f"{{{W}}}{tag}"


def m(tag: str) -> str:
    return f"{{{M}}}{tag}"


def render(formulas: list[dict]) -> list[etree._Element]:
    """Render every formula with pandoc, one per paragraph, preserving order."""
    import pypandoc  # imported lazily: documents without maths don't need pandoc

    md = "\n\n".join(
        f"$$\n{f['latex']}\n$$" if f["display"] else f"${f['latex']}$" for f in formulas
    )
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "math.docx"
        pypandoc.convert_text(md, "docx", format="markdown", outputfile=str(out))
        doc = etree.fromstring(zipfile.ZipFile(out).read("word/document.xml"))

    rendered = []
    for p in doc.find(w("body")).iter(w("p")):
        node = p.find(f".//{m('oMathPara')}")
        if node is None:
            node = p.find(f".//{m('oMath')}")
        if node is not None:
            rendered.append(node)
    if len(rendered) != len(formulas):
        raise SystemExit(f"pandoc rendered {len(rendered)} equations for {len(formulas)} formulas")

    for f, node in zip(formulas, rendered, strict=True):
        want = "oMathPara" if f["display"] else "oMath"
        if etree.QName(node).localname != want:
            raise SystemExit(
                f"formula {f['latex']!r}: expected {want}, got {etree.QName(node).localname}"
            )
        schema_fix(node)
    return rendered


def schema_fix(node: etree._Element) -> None:
    """Pandoc's OMML deviates from the OOXML schema in two places (Word tolerates both)."""
    for rpr in node.iter(m("rPr")):  # m:rPr allows nor XOR (scr?, sty?)
        if rpr.find(m("nor")) is not None:
            for sty in rpr.findall(m("sty")):
                rpr.remove(sty)
    order = {"count": 0, "mcJc": 1}  # m:mcPr sequence is count?, mcJc?
    for mcpr in node.iter(m("mcPr")):
        for child in sorted(mcpr, key=lambda e: order.get(etree.QName(e).localname, 9)):
            mcpr.append(child)


def match_size(eq: etree._Element, size: str) -> None:
    """Give every equation run the surrounding font size (e.g. smaller table text)."""
    for mr in eq.iter(m("r")):
        rpr = mr.find(w("rPr"))
        if rpr is None:
            rpr = etree.Element(w("rPr"))
            mrpr = mr.find(m("rPr"))  # schema order: m:rPr, w:rPr, m:t
            if mrpr is not None:
                mrpr.addnext(rpr)
            else:
                mr.insert(0, rpr)
        for tag in ("sz", "szCs"):
            el = rpr.find(w(tag))
            if el is None:
                el = etree.SubElement(rpr, w(tag))
            el.set(w("val"), size)


def fill(src: Path, dst: Path) -> int:
    formulas = json.loads(Path(f"{src}.math.json").read_text(encoding="utf-8"))
    if not formulas:
        shutil.copyfile(src, dst)
        return 0
    rendered = render(formulas)

    zin = zipfile.ZipFile(src)
    doc = etree.fromstring(zin.read("word/document.xml"))

    # Collect first, then replace: never mutate the tree while iterating it.
    targets = []
    for r in doc.iter(w("r")):
        t = r.find(w("t"))
        hit = PLACEHOLDER.fullmatch(t.text) if t is not None and t.text else None
        if hit:
            targets.append((r, int(hit.group(1))))

    for r, n in targets:
        eq = copy.deepcopy(rendered[n])
        size = r.find(f"{w('rPr')}/{w('sz')}")
        if size is not None:
            match_size(eq, size.get(w("val")))
        para = r.getparent()
        alone = not any(
            other is not r and "".join(other.itertext()).strip() for other in para.iter(w("r"))
        )
        para.replace(r, eq)
        if alone and not formulas[n]["display"]:
            # An equation alone in a paragraph is laid out as display maths (centred);
            # a zero-width space keeps it inline, e.g. in table cells.
            run = etree.SubElement(para, w("r"))
            etree.SubElement(run, w("t")).text = ZERO_WIDTH_SPACE

    missing = sorted(set(range(len(formulas))) - {n for _, n in targets})
    if missing:
        raise SystemExit(f"placeholders not found for formulas {missing}")

    xml = etree.tostring(doc, xml_declaration=True, encoding="UTF-8", standalone=True)
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            data = xml if item.filename == "word/document.xml" else zin.read(item.filename)
            zout.writestr(item, data)
    return len(targets)


def main(argv: list[str]) -> None:
    if len(argv) != 2:
        raise SystemExit("usage: python mathfill.py in.docx out.docx")
    n = fill(Path(argv[0]), Path(argv[1]))
    print(f"inserted {n} equations -> {argv[1]}")


if __name__ == "__main__":
    main(sys.argv[1:])
