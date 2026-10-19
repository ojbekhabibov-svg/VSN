#!/usr/bin/env python3
"""OCR PDF-документов без .htm (их текстовый слой — старый OCR с разрывами слов).

Запуск: python ocr_shard.py <shard> <total> <out_dir>
Берёт документы, у которых есть PDF и нет HTM, с int(id) % total == shard;
пропускает те, у которых в text/ уже есть версия «Источник текста: ocr».
Результат: <out_dir>/<id>.txt — страницы, разделённые символом \\f.
"""
import concurrent.futures as cf
import csv
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(os.environ.get("OUT_DIR", ".")).resolve()
DPI = os.environ.get("OCR_DPI", "250")


def ocr_page(img):
    r = subprocess.run(["tesseract", str(img), "-", "-l", "rus+eng", "--psm", "3"],
                       capture_output=True, timeout=900)
    return r.stdout.decode("utf-8", "replace")


def main():
    shard, total, out = int(sys.argv[1]), int(sys.argv[2]), Path(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(Path(__file__).parent))
    from build_registers import slug

    rows = list(csv.DictReader(open(ROOT / "index.csv", encoding="utf-8-sig"), delimiter=";"))
    todo = []
    for r in rows:
        if not r["pdf_path"] or r["htm_path"] or not r["id"].isdigit() or int(r["id"]) % total != shard:
            continue
        t = ROOT / "text" / (slug(r["number"], r["id"]) + ".md")
        if t.exists() and "Источник текста: ocr" in t.read_text(encoding="utf-8")[:1500]:
            continue
        if (ROOT / r["pdf_path"]).exists():
            todo.append(r)
    print(f"shard {shard}/{total}: документов {len(todo)}", flush=True)
    workers = os.cpu_count() or 2
    for i, r in enumerate(todo, 1):
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(["pdftoppm", "-r", DPI, "-gray", str(ROOT / r["pdf_path"]), f"{tmp}/p"],
                           capture_output=True, timeout=3600)
            imgs = sorted(Path(tmp).glob("p*.pgm"))
            with cf.ThreadPoolExecutor(workers) as ex:
                pages = list(ex.map(ocr_page, imgs))
        (out / f"{r['id']}.txt").write_text("\f".join(pages), encoding="utf-8")
        print(f"[{i}/{len(todo)}] {r['number']} — {len(imgs)} стр.", flush=True)


if __name__ == "__main__":
    main()
