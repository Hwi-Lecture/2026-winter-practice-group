from docx import Document
from docx.oxml.ns import qn

SRC = "키키테크_사내규정_행동강령.docx"
DST = "키키테크_사내규정_행동강령.txt"


def para_text(p):
    """문단 안의 모든 텍스트(sdt/hyperlink 등 래퍼 안쪽 포함)를 순서대로 이어 붙인다."""
    parts = []
    for el in p.iter():
        if el.tag == qn("w:t"):
            parts.append(el.text or "")
        elif el.tag == qn("w:tab"):
            parts.append("\t")
        elif el.tag in (qn("w:br"), qn("w:cr")):
            parts.append("\n")
    return "".join(parts)


def walk(container, lines):
    """본문을 문서 순서대로 훑으며 문단/표(중첩 포함)를 추출한다."""
    for child in container.iterchildren():
        if child.tag == qn("w:p"):
            lines.append(para_text(child))
        elif child.tag == qn("w:tbl"):
            for tr in child.iter(qn("w:tr")):
                cells = []
                for tc in tr.iterchildren(qn("w:tc")):
                    cells.append(" ".join(para_text(p) for p in tc.iter(qn("w:p"))).strip())
                lines.append("\t".join(cells))
        elif child.tag == qn("w:sdt"):
            content = child.find(qn("w:sdtContent"))
            if content is not None:
                walk(content, lines)


doc = Document(SRC)
lines = []
walk(doc.element.body, lines)

with open(DST, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"저장 완료: {DST} ({len(lines)}줄)")
