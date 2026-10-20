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
    s = s.upper().replace("—", "-").replace("–", "-")
    s = re.sub(r"^\s*(?:ВСН|BCH|ВНЭ)[\s-]*(?:АПК|АС|ВК)?[\s-]*", "", s)
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
    for inner in re.findall(r"ВСН\s*[\d.\-]+", name):  # «ВСН 512-88. …» внутри названия
        if any(sim(name, d["name"]) >= 0.4 for d in have.get(norm(inner), [])):
            return True
    if any(sim(number + " " + name, d["name"]) >= 0.8 for d in have.get(norm(number), [])):
        return True
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


# Ручная оценка значимости для работ PBG (газопроводы, КС/ГРС, ЭХЗ, сварка, ППР): номер -> (приоритет, пояснение, [статус])
MANUAL = {
    "39-1.22-007-2002": ("Высокий", "Вставки электроизолирующие для газопроводов (Газпром) — дополняет ВСН 39-1.8-008-2002"),
    "174-84": ("Высокий", "В открытом доступе не найден (поиск 20.10.2026) — искать в фондах/у заказчика. Катодная защита промысловых сооружений; ссылается ВСН 009-88"),
    "211-87": ("Высокий", "В открытом доступе не найден (поиск 20.10.2026) — искать в фондах/у заказчика. ЭХЗ кожухов на переходах под авто- и ж/д дорогами; ссылается ВСН 009-88"),
    "193-86": ("Высокий", "В открытом доступе не найден (поиск 20.10.2026) — искать в фондах/у заказчика. Геотекстиль (ГСМ) при балластировке трубопроводов грунтом; ссылается ВСН 007-88"),
    "219-87": ("Высокий", "В открытом доступе не найден (поиск 20.10.2026) — искать в фондах/у заказчика. Подготовительные работы и временные дороги при строительстве трубопроводов — прямая ссылка в ВСН 003-88 п. 7.2"),
    "177-84": ("Высокий", "В открытом доступе не найден (поиск 20.10.2026) — искать в фондах/у заказчика. Метрологическое обеспечение подготовительных и земляных работ на МТ; ссылается ВСН 012-88",
               "Инструкция по метрологическому обеспечению производства подготовительных и земляных работ при сооружении магистральных трубопроводов"),
    "267-73": ("Высокий", "В открытом доступе не найден (поиск 20.10.2026) — искать в фондах/у заказчика. Термообработка сварных соединений технологических трубопроводов (ММСС); ссылается ВСН 70-79"),
    "155-83": ("Средний", "ЭХЗ подземных трубопроводов в северных районах (региональная специфика)"),
    "216-87": ("Средний", "Сварка вращающейся дугой труб Ø32–60 мм"),
    "2-88-77": ("Средний", "Безопасность при радиоизотопной дефектоскопии (РК стыков)"),
    "313-73": ("Средний", "Деталировочные чертежи технологических трубопроводов высокого давления"),
    "600-81": ("Средний", "Линейные сооружения связи (кабели связи вдоль МГ, подводные кабельные переходы)"),
    "187-85": ("Средний", "Полевой городок (вахтовый посёлок) — для ПОС/ППР; ссылается ВСН 004-88"),
    "30-77": ("Средний", "ТБ для машиниста трубоукладчика (не путать с ВСН 30-77 по кондиционированию)"),
    "389-77": ("Средний", "Защитные покрытия тепловой изоляции оборудования и трубопроводов"),
    "020-69": ("Средний", "Геотехнический контроль в энергетическом строительстве"),
    "2661-01-91": ("Средний", "Автоматические установки пожаротушения — производство и приёмка работ"),
    "2-43-74": ("Низкий", "Автосварка под флюсом на трубосварочных базах (старая серия ВНИИСТ, вероятно заменена ВСН 006-89)"),
    "1-24-78": ("Низкий", "«Сварочно-монтажные работы» (старая серия ВНИИСТ, заменена ВСН 006-89)"),
    "I-31-71": ("Низкий", "Балластировка грунтом (старая серия ВНИИСТ, заменена ВСН 007-88)"),
    "2-52-75": ("Низкий", "Совмещённое строительство вдольтрассовой ЛЭП (в библиотеке есть более новая ВСН 195-86)"),
    "213-83": ("Низкий", "Блочное проектирование объектов НПЗ"), "215-84": ("Низкий", "Блочное проектирование объектов НПЗ"),
    "453-84": ("Низкий", "Блочное проектирование (ММСС)"), "354-75": ("Низкий", "Нормы теплопотерь (ММСС)"),
    "399-79": ("Низкий", "Тепловая изоляция — коэффициенты стоимости (ММСС)"),
    "368-76": ("Низкий", ""), "376-77": ("Низкий", ""), "333-74": ("Низкий", ""), "191-83": ("Низкий", ""), "235-88": ("Низкий", ""),
    "АС 90": ("Низкий", ""), "25-80": ("Низкий", ""), "145-68": ("Низкий", ""), "122-65": ("Низкий", ""),
    "600-IV-87": ("Низкий", "ТБ при монтаже оборудования связи"),
}
MANUAL_STATUS = {  # номера, которые на деле не являются недостающими
    "440-53": ("Ошибка распознавания", "= ВСН 440-83 (Киевский филиал ВНИИМонтажспецстроя, 1983) — есть в библиотеке"),
    "411-87": ("Ошибка распознавания", "опечатка в ВСН 362-87, имеется в виду ВСН 411-88 — есть в библиотеке"),
    "2-12-80": ("Ошибка распознавания", "опечатка в ВСН 1-84, имеется в виду ВСН 2-124-80 — есть в библиотеке"),
    "311-73": ("Есть другая редакция", "в библиотеке более новая: ВСН 311-89 «Монтаж стальных вертикальных цилиндрических резервуаров…»"),
    "2-65-76": ("Заменён", "заменён ВСН 2-144-82 («Ввамен» на титуле) — есть в библиотеке"),
    "2-104-78": ("Заменён", "заменён ВСН 2-144-82 («Ввамен» на титуле) — есть в библиотеке"),
}


def prio(dirs, text):
    ds = set(dirs[:3])
    if ds & (HIGH | MID):
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

def base(n):
    p = n.rsplit("-", 1)
    return p[0] if len(p) == 2 and re.fullmatch(r"\d{2}", p[1]) else None


def yr(n):
    y = int(n.rsplit("-", 1)[1])
    return y + (1900 if y > 30 else 2000)


have_base = collections.defaultdict(list)
for h in have:
    if base(h):
        have_base[base(h)].append(h)
refs_by_num = {norm(x["num"]): x for x in refs}
superseded = []

# ---------- объединение
final = {}
for k, e in catalog_missing.items():
    n = norm(e["number"])
    newer = [d for h in have_base.get(base(n) or "-", []) for d in have[h]
             if sim(e["name"], d["name"]) >= 0.5 and yr(h) > yr(n)] if base(n) else []
    rx = refs_by_num.get(n)
    if newer:
        superseded.append(dict(num=e["number"], status="Есть другая редакция",
                               note=f"в библиотеке более новая: {newer[0]['number']} «{newer[0]['name'][:70]}» (по каталогу: {e['status']})",
                               title=e["name"], by=[]))
        continue
    if rx and rx["status"] == "Заменён":
        superseded.append(dict(num=e["number"], status="Заменён", note=rx["note"] + f" (по каталогу meganorm: {e['status']})",
                               title=e["name"], by=rx["by"]))
        continue
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
        row["prio"] = prio(row["dirs"], row["name"])
        row["org"] = x["org"]
    else:
        final[k] = dict(number=x["num"], name=x["title"], org=x["org"], date="", cat_status="",
                        found_in="ссылки в ВСН (нет в каталогах meganorm)", links="", refs_n=x["n_by"],
                        refs_by=", ".join(x["by"]), dirs=x["dirs"], prio=prio(x["dirs"], x["title"]), note=x["note"])

for k in list(final):
    key = k if k in MANUAL or k in MANUAL_STATUS else re.sub(r"^(АС)\s*", r"\1 ", k)
    if key in MANUAL_STATUS:
        st, nt = MANUAL_STATUS[key]
        superseded.append(dict(num=final[k]["number"], status=st, note=nt, title=final[k]["name"], by=final[k]["refs_by"].split(", ") if final[k]["refs_by"] else []))
        del final[k]
        continue
    if final[k]["refs_by"] and all(re.search(r"Минобороны|МО ", b) for b in final[k]["refs_by"].split(", ")):
        final[k]["prio"] = "Низкий"
    if final[k]["name"] and (not re.match(r"[«\"]?[А-ЯЁA-Z]", final[k]["name"]) or "<" in final[k]["name"]):
        final[k]["name"] = ""
    if key in MANUAL:
        final[k]["prio"], why = MANUAL[key][0], MANUAL[key][1]
        if len(MANUAL[key]) > 2:
            final[k]["name"] = MANUAL[key][2]
        if why:
            final[k]["note"] = why + ("; " + final[k]["note"] if final[k]["note"] else "")
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
    ws.freeze_panes = f"A{row + 1}"


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
for i, x in enumerate(sorted([x for x in refs if x["status"] != "Отсутствует" and norm(x["num"]) not in {norm(y["num"]) for y in superseded}] + superseded,
                              key=lambda x: (order[x["status"]], x["num"])), 1):
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
fs = collections.Counter(MANUAL_STATUS.get(norm(x["num"]), (x["status"],))[0] for x in refs)
lines = [
    ("Анализ недостающих ВСН в библиотеке ojbekhabibov-svg/VSN", None),
    ("", None),
    ("В библиотеке документов", len(idx)),
    ("Источник 1: номера ВСН, упомянутые в текстах библиотеки (уникальных, отсутствующих)", len(refs)),
    ("   — заменены документами, которые есть в библиотеке", fs.get("Заменён", 0)),
    ("   — в библиотеке есть другая (обычно более новая) редакция", fs.get("Есть другая редакция", 0)),
    ("   — ошибки распознавания номера (не документы)", fs.get("Ошибка распознавания", 0)),
    ("   — действительно отсутствуют", fs.get("Отсутствует", 0)),
    ("Источник 2: ВСН в других базах meganorm (База 1, «Актуальные документы»), которых нет в библиотеке", len(catalog_missing)),
    ("   — из них есть более новая редакция или заменены (лист «Не требуются»)", len(superseded)),
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
