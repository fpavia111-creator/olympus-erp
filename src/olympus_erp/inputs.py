"""CSV / XLSX reader. XLSX intentionally supports values, not macros or formulas."""
import csv
import re
from datetime import datetime, timedelta
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile, BadZipFile

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "p": "http://schemas.openxmlformats.org/package/2006/relationships"}

# Total uncompressed XLSX size. ElementTree parses whole parts in memory, so this bounds RAM
# (about 10x the XML size) even for a small, highly compressed upload.
MAX_XLSX_UNCOMPRESSED = 25_000_000

class SourceError(ValueError):
    pass

def _cidx(cell_ref):
    letters = re.match(r"[A-Z]+", cell_ref or "A")
    n = 0
    for c in letters.group(0):
        n = n * 26 + ord(c) - 64
    return n - 1

def _xlsx_rows(path, sheet=None):
    try:
        with ZipFile(path) as z:
            if len(z.namelist()) > 2000 or sum(i.file_size for i in z.infolist()) > MAX_XLSX_UNCOMPRESSED:
                raise SourceError("XLSX exceeds local safety limits")
            main = ET.fromstring(z.read("xl/workbook.xml"))
            relationships = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
            rels = {r.get("Id"): r.get("Target") for r in relationships}
            sheets = main.find("m:sheets", NS)
            found = None
            for s in (sheets if sheets is not None else []):
                if (sheet is None and found is None) or (sheet and s.get("name") == sheet):
                    found = s
                    if sheet:
                        break
            if found is None:
                raise SourceError(f"Worksheet not found: {sheet}")
            rel = found.get(f"{{{NS['r']}}}id")
            target = rels.get(rel, "")
            name = target.lstrip("/") if target.startswith("/") else (target if target.startswith("xl/") else "xl/" + target)
            # Normalize worksheet paths; disallow zip path traversal.
            from posixpath import normpath
            name = normpath(name)
            if not name.startswith("xl/") or ".." in name.split("/"):
                raise SourceError("Unsafe XLSX worksheet reference")
            shared = []
            if "xl/sharedStrings.xml" in z.namelist():
                ss = ET.fromstring(z.read("xl/sharedStrings.xml"))
                shared = ["".join(t.text or "" for t in si.findall(".//m:t", NS)) for si in ss.findall("m:si", NS)]
            date_styles = set()
            if "xl/styles.xml" in z.namelist():
                styles = ET.fromstring(z.read("xl/styles.xml"))
                fmts = styles.find("m:numFmts", NS)
                custom = {int(f.get("numFmtId")): f.get("formatCode", "") for f in (fmts or [])}
                cell_xfs = styles.find("m:cellXfs", NS)
                for idx, xf in enumerate(cell_xfs or []):
                    n = int(xf.get("numFmtId", 0))
                    fmt = re.sub(r'"[^"]*"|\\.', '', custom.get(n, "")).lower()
                    if n in set(range(14, 23)) or (fmt and re.search(r"[dmy]", fmt)):
                        date_styles.add(idx)
            pr = main.find("m:workbookPr", NS)
            epoch = datetime(1904, 1, 1) if (pr is not None and pr.get("date1904") == "1") else datetime(1899, 12, 30)
            xml = ET.fromstring(z.read(name))
            sheetdata = xml.find("m:sheetData", NS)
            result = []
            for row in (sheetdata if sheetdata is not None else []):
                cells = {}
                for cell in row.findall("m:c", NS):
                    idx = _cidx(cell.get("r"))
                    kind = cell.get("t", "")
                    if cell.find("m:f", NS) is not None:
                        raise SourceError("XLSX contains formulas; paste values and save a new workbook before importing")
                    value = cell.find("m:v", NS)
                    if kind == "inlineStr":
                        text = "".join(t.text or "" for t in cell.findall(".//m:is/m:t", NS))
                    elif kind == "s" and value is not None:
                        text = shared[int(value.text or 0)]
                    elif kind in ("str", "b", "e") and value is not None:
                        text = value.text or ""
                    elif value is not None:
                        text = value.text or ""
                        if int(cell.get("s", 0)) in date_styles and text:
                            try:
                                text = (epoch + timedelta(days=float(text))).strftime("%Y-%m-%d")
                            except (OverflowError, ValueError):
                                pass
                    elif cell.find("m:f", NS) is not None:
                        raise SourceError("XLSX formula without cached result: recalculate and save in Excel first")
                    else:
                        text = ""
                    cells[idx] = text
                if cells:
                    seq = [cells.get(i, "") for i in range(max(cells) + 1)]
                    result.append((int(row.get("r", len(result) + 1)), seq))
            return result
    except (BadZipFile, ET.ParseError, KeyError, IndexError, ValueError) as exc:
        if isinstance(exc, SourceError):
            raise
        raise SourceError(f"Invalid or unsupported XLSX file: {exc}") from exc

def read_rows(path, sheet=None):
    path = Path(path)
    if not path.is_file():
        raise SourceError(f"File not found: {path}")
    if path.stat().st_size > 60_000_000:
        raise SourceError("Source exceeds 60 MB local limit")
    if path.suffix.lower() == ".xlsx":
        rows = _xlsx_rows(path, sheet)
    elif path.suffix.lower() in (".csv", ".txt"):
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            rdr = csv.reader(f)
            rows = []
            previous_line = 0
            for record in rdr:
                start = previous_line + 1
                previous_line = rdr.line_num
                if record and any(x.strip() for x in record):
                    rows.append((start, record))
    else:
        raise SourceError("Only .csv or .xlsx inputs are supported")
    if not rows:
        raise SourceError(f"No rows: {path}")
    hdr = [x.strip() for x in rows[0][1]]
    if not hdr or any(not x for x in hdr) or len(set(hdr)) != len(hdr):
        raise SourceError("Headers must be nonblank and unique")
    result = []
    for line, seq in rows[1:]:
        if len(seq) > len(hdr) and any(x.strip() for x in seq[len(hdr):]):
            raise SourceError(f"Extra cells at line {line}")
        result.append((line, dict(zip(hdr, (seq + [""] * len(hdr))[:len(hdr)]))))
    return hdr, result

def profile(path, sheet=None):
    cols, rows = read_rows(path, sheet)
    return {"file": str(path), "rows": len(rows), "columns": cols, "missing": {
        c: sum(not r[c].strip() for _, r in rows) for c in cols},
        "sample_line_numbers": [line for line, _ in rows[:5]]}
