"""文档解析：PDF / Word / Excel / Markdown / TXT → 带页码（工作表/页）的文本块。

PDF 优先用 pdfplumber：
- 表格识别后转成 Markdown 表格，保留行列关系（否则单元格会被拍平成一行一个词）；
- 表格区域从正文里剔除，避免同一份内容重复入库；
- pdfplumber 失败时回退到 pypdf，保证不因个别 PDF 直接失败。

Excel（.xlsx/.xlsm）每个工作表转成一张 Markdown 表，工作表序号作为页码，
文件名 + 工作表名写进正文，保证回答能定位到"哪份文件的哪个 sheet"。
"""
from __future__ import annotations

from pathlib import Path

TABLE_MARK = "【表格】"
MAX_SHEET_ROWS = 5000  # 单表最多读取行数，避免超大表把索引撑爆


def parse_file(path: str) -> list[dict]:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".pdf":
        return _parse_pdf(p)
    if suffix == ".docx":
        return _parse_docx(p)
    if suffix in {".xlsx", ".xlsm"}:
        return _parse_excel(p)
    if suffix == ".xls":
        raise ValueError("旧版 .xls 不支持，请在 Excel 里另存为 .xlsx 后重新上传")
    if suffix in {".md", ".markdown", ".txt"}:
        text = p.read_text(encoding="utf-8", errors="ignore")
        return [{"text": text, "page": 1}]
    raise ValueError(f"不支持的文件类型：{suffix}")


# ---------------------------------------------------------------- Excel
def _cell_text(v) -> str:
    """单元格取值规范化：去掉浮点尾巴、空值统一空串。"""
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).replace("\n", " ").strip()


def _parse_excel(p: Path) -> list[dict]:
    from openpyxl import load_workbook

    try:
        wb = load_workbook(str(p), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"Excel 打开失败（文件可能损坏或被加密）：{exc}") from exc

    blocks: list[dict] = []
    try:
        for idx, ws in enumerate(wb.worksheets, start=1):
            rows: list[list[str]] = []
            for raw in ws.iter_rows(values_only=True):
                cells = [_cell_text(v) for v in raw]
                while cells and cells[-1] == "":
                    cells.pop()
                if any(cells):
                    rows.append(cells)
                if len(rows) >= MAX_SHEET_ROWS:
                    break

            if not rows:
                continue

            md = _table_to_markdown(rows)
            if not md:  # 只有一行时 _table_to_markdown 返回空，退化成普通行
                md = "\n".join(" | ".join(r) for r in rows)

            header = f"文件：{p.name}　工作表：{ws.title}（共 {len(rows)} 行）"
            text = _clean(f"{header}\n{TABLE_MARK}\n{md}")
            if text:
                blocks.append({"text": text, "page": idx})
    finally:
        wb.close()

    if not blocks:
        raise ValueError("Excel 中没有可提取的数据（所有工作表都是空的）")
    return blocks


# ---------------------------------------------------------------- PDF
def _parse_pdf(p: Path) -> list[dict]:
    try:
        blocks = _parse_pdf_plumber(p)
        if blocks:
            return blocks
    except Exception:  # noqa: BLE001  解析器异常时回退
        pass
    return _parse_pdf_pypdf(p)


def _table_to_markdown(rows: list[list[str | None]]) -> str:
    cleaned = []
    for row in rows:
        cells = [(c or "").replace("\n", " ").strip() for c in row]
        if any(cells):
            cleaned.append(cells)
    if len(cleaned) < 2:
        return ""
    width = max(len(r) for r in cleaned)
    cleaned = [r + [""] * (width - len(r)) for r in cleaned]
    header, body = cleaned[0], cleaned[1:]
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join(["---"] * width) + "|"]
    for row in body:
        lines.append("| " + " | ".join(row) + " |")
    return "\n".join(lines)


def _parse_pdf_plumber(p: Path) -> list[dict]:
    import pdfplumber

    blocks: list[dict] = []
    with pdfplumber.open(str(p)) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            tables = []
            try:
                found = page.find_tables()
            except Exception:  # noqa: BLE001
                found = []

            bboxes = []
            for t in found:
                try:
                    md = _table_to_markdown(t.extract())
                except Exception:  # noqa: BLE001
                    md = ""
                if md:
                    tables.append(md)
                    bboxes.append(t.bbox)

            # 正文：剔除表格区域，避免与 Markdown 表格重复
            text = ""
            try:
                if bboxes:

                    def _outside(obj) -> bool:
                        x0, top = obj.get("x0", 0), obj.get("top", 0)
                        for bx0, btop, bx1, bbottom in bboxes:
                            if bx0 - 1 <= x0 <= bx1 + 1 and btop - 1 <= top <= bbottom + 1:
                                return False
                        return True

                    text = page.filter(_outside).extract_text() or ""
                else:
                    text = page.extract_text() or ""
            except Exception:  # noqa: BLE001
                text = ""

            parts = []
            body = _clean(text)
            if body:
                parts.append(body)
            if tables:
                labeled = [f"{TABLE_MARK} {i}\n{md}" for i, md in enumerate(tables, start=1)]
                parts.append("\n\n".join(labeled))

            merged = _clean("\n\n".join(parts))
            if merged:
                blocks.append({"text": merged, "page": page_no})

    if not blocks:
        raise ValueError("PDF 中没有可提取的文本（可能是扫描件，需要 OCR）")
    return blocks


def _parse_pdf_pypdf(p: Path) -> list[dict]:
    from pypdf import PdfReader

    reader = PdfReader(str(p))
    blocks: list[dict] = []
    for i, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        text = _clean(text)
        if text:
            blocks.append({"text": text, "page": i})
    if not blocks:
        raise ValueError("PDF 中没有可提取的文本（可能是扫描件，需要 OCR）")
    return blocks


# ---------------------------------------------------------------- DOCX
def _parse_docx(p: Path) -> list[dict]:
    import docx

    doc = docx.Document(str(p))
    parts: list[str] = []
    table_seq = 0
    for para in doc.paragraphs:
        if para.text.strip():
            parts.append(para.text.strip())

    for table in doc.tables:
        rows: list[list[str | None]] = []
        for row in table.rows:
            rows.append([c.text.strip() for c in row.cells])
        md = _table_to_markdown(rows)
        if md:
            table_seq += 1
            parts.append(f"{TABLE_MARK} {table_seq}\n{md}")

    text = _clean("\n\n".join(parts))
    if not text:
        raise ValueError("DOCX 中没有可提取的文本")
    return [{"text": text, "page": 1}]


def _clean(text: str) -> str:
    """清洗：去控制字符、合并连续空行（保留段落分隔）、去掉紧邻重复行。"""
    text = (text or "").replace("\r\n", "\n").replace("\x00", "")
    out: list[str] = []
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            if out and out[-1] != "":
                out.append("")
            continue
        if out and line == out[-1]:
            continue
        out.append(line)
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out).strip()