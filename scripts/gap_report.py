#!/usr/bin/env python3
"""Отчёт «Недостающие ВСН» (Excel) из двух источников:
 1) ссылки на ВСН внутри текстов библиотеки (scripts/gap_refs.py -> registers/_gap_refs.json);
 2) каталоги других баз meganorm / files.stroyinf (scripts/crawl_catalogs.py -> catalogs/sources.csv).
Выход: registers/Недостающие_ВСН.xlsx
"""
import collections
import csv
import json
import re
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

ROOT = Path(".")
idx = json.load(open(ROOT / "registers/registers.json", encoding="utf-8"))


def norm(s):
    s = s.upper().replace("ВСН", "").replace("BCH", "").replace("—", "-").replace("–", "-")
    s = re.sub(r"\s*-\s*", "-", s.strip())
    m = re.match(r"((?:[IVX]+-)?\d+(?:[.\-]\d+)*)", s.replace(" ", ""))
    return m.group(1) if m else ""


STOP = set("по и в на для при с из от к о об а также или их его ее не что как".split())


def words(t):
    return {w[:6] for w in re.findall(r"[а-яё]{4,}", t.lower()) if w not in STOP}


def sim(a, b):
    A, B = words(a), words(b)
    return len(A & B) / max(1, min(len(A), len(B))) if A and B else 0


have = collections.defaultdict(list)
for d in idx:
    n = norm(d["number"])
    if n:
        have[n].append(d)


def in_library(number, name):
    n = norm(number)
    if not n:  # б/н — по названию
        return any(sim(name, d["name"]) >= 0.8 for d in idx)
    return any(sim(name, d["name"]) >= 0.45 or not name for d in have.get(n, []))


HIGH = {"LCH", "TT", "SV", "AKZ", "ISP"}
MID = {"ZR", "BZB", "MK", "ORG", "OT", "EL", "IS", "OOS", "PB"}
OILGAS = re.compile(r"(?i)нефт|газ|трубопровод|компрессор|резервуар|сварк|изоляц|коррози|электрохим|катодн|ВНИИСТ")
KEYWORDS = {
    "LCH": r"магистральн|промыслов|трубопровод", "TT": r"технологическ\w* (?:трубопр|оборуд)|компрессор|резервуар|монтаж\w* оборуд",
    "SV": r"сварк|сварн|резк", "AKZ": r"изоляц|коррози|электрохим|катодн|теплоизол", "ISP": r"испытан|приемк|контрол",
    "ZR": r"грунт|земл|свай|фундамент|основан", "BZB": r"бетон|раствор", "ORG": r"организац|норм\w* расход|продолжительн|смет|ппр|проект\w* производств",
    "OT": r"безопасн", "EL": r"электр|связ|освещ|автоматиз", "IS": r"водопровод|канализ|тепл\w* сет|вентил|отоплен",
}


def guess_dirs(name):
    t = name.lower()
    return [k for k, rx in KEYWORDS.items() if re.search(rx, t)]


def prio(dirs, text):
    ds = set(dirs[:3])
    if ds & HIGH or OILGAS.search(text):
        return "Высокий"
    if ds & MID:
        return "Средний"
    return "Низкий"


# ---------- 1) ссылки
refs = json.load(open(ROOT / "registers/_gap_refs.json", encoding="utf-8"))
# ---------- 2) каталоги
cat_rows = []
src = ROOT / "catalogs/sources.csv"
if src.exists():
    cat_rows = list(csv.DictReader(open(src, encoding="utf-8-sig"), delimiter=";"))

catalog_missing = {}
for r in cat_rows:
    num = r["number"].strip()
    if not re.search(r"(?i)ВСН|ВНЭ|BCH", num + r["name"][:20]):
        continue
    if in_library(num, r["name"]):
        continue
    key = (norm(num) or r["name"][:60].lower())
    e = catalog_missing.setdefault(key, dict(number=num, name=r["name"], date=r["date"], status=r["status"], links=set(), sources=set()))
    e["links"].update(x for x in r["links"].split() if x)
    e["sources"].add(r["source"].split(":")[0])
    if len(r["name"]) > len(e["name"]):
        e["name"] = r["name"]

# ---------- объединение
final = {}
for k, e in catalog_missing.items():
    dirs = guess_dirs(e["name"])
    final[k] = dict(number=e["number"], name=e["name"], org="", date=e["date"], cat_status=e["status"],
                    found_in="каталог: " + ", ".join(sorted(e["sources"])),
                    links=" ".join(sorted(e["links"]))[:500], refs_n=0, refs_by="", dirs=dirs,
                    prio=prio(dirs, e["name"]), note="")
for x in refs:
    if x["status"] != "Отсутствует":
        continue
    k = norm(x["num"])
    row = final.get(k)
    if row:
        row["found_in"] = "ссылки в ВСН + " + row["found_in"]
        row["refs_n"], row["refs_by"] = x["n_by"], ", ".join(x["by"])
        row["dirs"] = x["dirs"] or row["dirs"]
        row["prio"] = x["prio"] if x["prio"] == "Высокий" else row["prio"]
        row["org"] = x["org"]
    else:
        final[k] = dict(number=x["num"], name=x["title"], org=x["org"], date="", cat_status="",
                        found_in="ссылки в ВСН (нет в каталогах meganorm)", links="", refs_n=x["n_by"],
                        refs_by=", ".join(x["by"]), dirs=x["dirs"], prio=x["prio"], note=x["note"])

rows = sorted(final.values(), key=lambda r: ({"Высокий": 0, "Средний": 1, "Низкий": 2}[r["prio"]],
                                             0 if r["links"] else 1, -r["refs_n"], r["number"]))

# ---------- Excel
wb = Workbook()
thin = Side(style="thin", color="999999")
B = Border(left=thin, right=thin, top=thin, bottom=thin)
HF = PatternFill("solid", fgColor="CCFFFF")
PF = {"Высокий": PatternFill("solid", fgColor="F8CBAD"), "Средний": PatternFill("solid", fgColor="FFF2CC"),
      "Низкий": PatternFill("solid", fgColor="EDEDED")}
LINK = Font(name="Calibri", size=10, color="0563C1", underline="single")


def header(ws, cols, widths, row=1):
    for i, (c, w) in enumerate(zip(cols, widths), 1):
        cell = ws.cell(row=row, column=i, value=c)
        cell.font = Font(name="Calibri", size=10, bold=True)
        cell.fill = HF
        cell.border = B
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = ws.cell(row=row + 1, column=1)


ws = wb.active
ws.title = "Недостающие"
cols = ["№", "Номер", "Название", "Ведомство", "Приоритет", "Направления", "Где выявлен", "Ссылка для скачивания",
        "Упоминаний", "Упоминается в", "Дата / статус по каталогу", "Примечание"]
header(ws, cols, [5, 20, 70, 18, 11, 14, 28, 40, 11, 40, 22, 40])
for i, r in enumerate(rows, 1):
    first_link = r["links"].split()[0] if r["links"] else ""
    vals = [i, r["number"], r["name"] or "— (название не указано в ссылке)", r["org"], r["prio"], ", ".join(r["dirs"][:4]),
            r["found_in"], first_link, r["refs_n"] or "", r["refs_by"], " ".join(filter(None, [r["date"], r["cat_status"]])), r["note"]]
    ws.append(vals)
    rr = ws.max_row
    for c in range(1, len(cols) + 1):
        cell = ws.cell(row=rr, column=c)
        cell.border = B
        cell.font = Font(name="Calibri", size=10)
        cell.alignment = Alignment(vertical="top", wrap_text=c in (3, 7, 10, 12))
    ws.cell(row=rr, column=5).fill = PF[r["prio"]]
    if first_link:
        ws.cell(row=rr, column=8).hyperlink = first_link
        ws.cell(row=rr, column=8).font = LINK
ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{ws.max_row}"

ws2 = wb.create_sheet("Не требуются (справочно)")
cols2 = ["№", "Номер (как в ссылке)", "Вывод", "Пояснение", "Название по ссылке", "Упоминается в"]
header(ws2, cols2, [5, 20, 26, 70, 60, 40])
order = {"Заменён": 0, "Есть другая редакция": 1, "Ошибка распознавания": 2}
for i, x in enumerate(sorted([x for x in refs if x["status"] != "Отсутствует"], key=lambda x: (order[x["status"]], x["num"])), 1):
    ws2.append([i, x["num"], x["status"], x["note"], x["title"], ", ".join(x["by"])])
    for c in range(1, 7):
        ws2.cell(row=ws2.max_row, column=c).border = B
        ws2.cell(row=ws2.max_row, column=c).font = Font(name="Calibri", size=10)
        ws2.cell(row=ws2.max_row, column=c).alignment = Alignment(vertical="top", wrap_text=c in (4, 5, 6))
ws2.auto_filter.ref = f"A1:F{ws2.max_row}"

ws0 = wb.create_sheet("Сводка", 0)
ws0.column_dimensions["A"].width = 70
ws0.column_dimensions["B"].width = 14
c = collections.Counter(r["prio"] for r in rows)
cs = collections.Counter(x["status"] for x in refs)
lines = [
    ("Анализ недостающих ВСН в библиотеке ojbekhabibov-svg/VSN", None),
    ("", None),
    ("В библиотеке документов", len(idx)),
    ("Источник 1: номера ВСН, упомянутые в текстах библиотеки (уникальных, отсутствующих)", len(refs)),
    ("   — заменены документами, которые есть в библиотеке", cs.get("Заменён", 0)),
    ("   — в библиотеке есть другая (обычно более новая) редакция", cs.get("Есть другая редакция", 0)),
    ("   — ошибки распознавания номера (не документы)", cs.get("Ошибка распознавания", 0)),
    ("   — действительно отсутствуют", cs.get("Отсутствует", 0)),
    ("Источник 2: ВСН в других базах meganorm / stroyinf, которых нет в библиотеке", len(catalog_missing)),
    ("", None),
    ("ИТОГО недостающих ВСН (лист «Недостающие»)", len(rows)),
    ("   — высокий приоритет (трубопроводы, ТТ, сварка, АКЗ/ЭХЗ, испытания, нефтегаз)", c.get("Высокий", 0)),
    ("   — средний (земляные, бетон, МК, ПОС/ППР, ОТ, электро, сети)", c.get("Средний", 0)),
    ("   — низкий (дороги, мосты, гидротехника, здания, прочие отрасли)", c.get("Низкий", 0)),
    ("   — из них есть ссылка для скачивания", sum(1 for r in rows if r["links"])),
    ("", None),
    ("Как читать: «Где выявлен» — ссылки в текстах ВСН и/или каталог другой базы; при наличии ссылки документ можно докачать.", None),
    ("Номера без названия взяты из перечней литературы — название уточняется по первоисточнику.", None),
]
for a, b in lines:
    ws0.append([a, b])
ws0["A1"].font = Font(name="Calibri", size=12, bold=True)
for rr in (11,):
    ws0.cell(row=rr, column=1).font = Font(name="Calibri", size=10, bold=True)
    ws0.cell(row=rr, column=2).font = Font(name="Calibri", size=10, bold=True)
wb.save(ROOT / "registers/Недостающие_ВСН.xlsx")
json.dump(rows, open(ROOT / "registers/_gap_final.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=list)
print("Недостающих:", len(rows), dict(c), "| с ссылкой:", sum(1 for r in rows if r["links"]),
      "| из каталогов:", len(catalog_missing))
