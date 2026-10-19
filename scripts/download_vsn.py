#!/usr/bin/env python3
"""
Скачивание всех ВСН со страницы meganorm.ru/list2/64505-0.htm.

- Парсит таблицу списка: номер, название, дата введения, статус, ссылки на PDF/HTM.
- Скачивает PDF и полнотекстовые .htm (Data2/...), а также картинки, на которые
  ссылаются .htm, сохраняя структуру папок сайта (чтобы картинки в .htm открывались).
- Пишет index.csv и README.md с таблицей-реестром.
- Возобновляемый: уже скачанные файлы пропускаются.
- Ограничение по объёму (MAX_TOTAL_MB): когда репозиторий заполнен, оставшиеся
  документы записываются в remaining.csv — их можно докачать в другой репозиторий.
"""
import csv
import html
import os
import re
import sys
import time
import urllib.parse
from pathlib import Path

import subprocess

import requests

BASE = "https://meganorm.ru"
LIST_URLS = [f"{BASE}/list2/64505-0.htm"]
ROOT = Path(os.environ.get("OUT_DIR", ".")).resolve()
FILES_DIR = ROOT / "files"
MAX_TOTAL_MB = float(os.environ.get("MAX_TOTAL_MB", "4500"))   # лимит на репозиторий
MAX_FILE_MB = 95                                               # GitHub: файл < 100 МБ
DELAY = float(os.environ.get("DELAY", "1.5"))
COMMIT_EVERY = int(os.environ.get("COMMIT_EVERY", "0"))   # 0 = не коммитить из скрипта
ONLY_IDS = set(filter(None, os.environ.get("ONLY_IDS", "").split(",")))  # для докачки в др. репо

S = requests.Session()
S.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Referer": BASE + "/",
})


def get(url, tries=4):
    for i in range(tries):
        try:
            r = S.get(url, timeout=120)
            if r.status_code == 200:
                return r
            if r.status_code == 404:
                return None
            print(f"  HTTP {r.status_code} {url}", flush=True)
        except requests.RequestException as e:
            print(f"  ERR {e} {url}", flush=True)
        time.sleep(5 * (i + 1))
    return None


def decode(r):
    for enc in ("utf-8", "cp1251"):
        try:
            return r.content.decode(enc)
        except UnicodeDecodeError:
            pass
    return r.content.decode("cp1251", errors="replace")


def strip_tags(s):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", s)).split())


def parse_list(text):
    docs = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", text, flags=re.S | re.I):
        cells = re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.S | re.I)
        if len(cells) < 4:
            continue
        links = re.findall(r'href="([^"]+)"', cells[0], flags=re.I)
        data = [urllib.parse.urljoin(BASE + "/list2/", l) for l in links if "/Data2/" in l]
        index = [urllib.parse.urljoin(BASE + "/list2/", l) for l in links if "/Index2/" in l]
        if not data and not index:
            continue
        m = re.search(r"/(\d+)\.htm", index[0] if index else data[0])
        doc_id = m.group(1) if m else ""
        docs.append({
            "id": doc_id,
            "number": strip_tags(re.findall(r"<a[^>]*>(.*?)</a>", cells[0], flags=re.S)[-1]),
            "name": strip_tags(cells[1]),
            "date": strip_tags(cells[2]),
            "status": strip_tags(cells[3]),
            "pdf_url": next((u for u in data if u.lower().endswith(".pdf")), ""),
            "htm_url": next((u for u in data if u.lower().endswith(".htm")), ""),
            "card_url": index[0] if index else "",
        })
    if not docs:  # запасной разбор: просто все ссылки Data2 на странице
        for u in sorted(set(re.findall(r'href="([^"]*/Data2/[^"]+\.(?:pdf|htm))"', text, flags=re.I))):
            u = urllib.parse.urljoin(BASE + "/list2/", u)
            m = re.search(r"/(\d+)\.(?:pdf|htm)$", u)
            docs.append({"id": m.group(1) if m else "", "number": "", "name": "", "date": "",
                         "status": "", "card_url": "",
                         "pdf_url": u if u.lower().endswith(".pdf") else "",
                         "htm_url": u if u.lower().endswith(".htm") else ""})
    return docs


def local_path(url):
    p = urllib.parse.urlparse(url).path.lstrip("/")
    return FILES_DIR / urllib.parse.unquote(p)


def dir_size_mb(p):
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file()) / 1048576 if p.exists() else 0


def save(url, dest):
    if dest.exists() and dest.stat().st_size > 0:
        return "exists"
    r = get(url)
    time.sleep(DELAY)
    if r is None:
        return "fail"
    if len(r.content) > MAX_FILE_MB * 1048576:
        return "too_big"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)
    return "ok"


def htm_assets(htm_url, dest):
    """Скачать картинки/стили, на которые ссылается полнотекстовый .htm."""
    raw = dest.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("cp1251", errors="replace")
    refs = set(re.findall(r'(?:src|href)="([^"#?]+\.(?:gif|png|jpe?g|bmp|css|wmf|emf|svg))"',
                          text, flags=re.I))
    for ref in refs:
        if ref.startswith(("http://", "https://")) and "meganorm.ru" not in ref:
            continue
        aurl = urllib.parse.urljoin(htm_url, ref)
        save(aurl, local_path(aurl))


def git_checkpoint(msg):
    if not COMMIT_EVERY:
        return
    subprocess.run(["git", "add", "-A", "files"], cwd=ROOT, check=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode == 0:
        return
    subprocess.run(["git", "commit", "-q", "-m", msg], cwd=ROOT, check=True)
    for _ in range(3):
        if subprocess.run(["git", "push", "-q"], cwd=ROOT).returncode == 0:
            print("  -> pushed:", msg, flush=True)
            return
        subprocess.run(["git", "pull", "-q", "--rebase"], cwd=ROOT)
    print("  !! push не удался", flush=True)


def main():
    docs, seen = [], set()
    for lu in LIST_URLS:
        r = get(lu)
        if not r:
            sys.exit(f"Не удалось получить список {lu}")
        for d in parse_list(decode(r)):
            key = (d["id"], d["pdf_url"], d["htm_url"])
            if key not in seen:
                seen.add(key)
                docs.append(d)
    print(f"В списке документов: {len(docs)}", flush=True)
    if not docs:
        sys.exit("Список пуст — вероятно, сайт заблокировал запрос.")

    remaining, stats = [], {}
    for i, d in enumerate(docs, 1):
        d["pdf_path"] = d["htm_path"] = ""
        d["note"] = ""
        if ONLY_IDS and d["id"] not in ONLY_IDS:
            continue
        if dir_size_mb(FILES_DIR) > MAX_TOTAL_MB:
            d["note"] = "не скачан: лимит репозитория"
            remaining.append(d)
            continue
        print(f"[{i}/{len(docs)}] {d['number']} — {d['name'][:70]}", flush=True)
        for kind in ("pdf", "htm"):
            url = d[f"{kind}_url"]
            if not url:
                continue
            dest = local_path(url)
            res = save(url, dest)
            stats[res] = stats.get(res, 0) + 1
            if res in ("ok", "exists"):
                d[f"{kind}_path"] = dest.relative_to(ROOT).as_posix()
                if kind == "htm":
                    htm_assets(url, dest)
            else:
                d["note"] += f"{kind}: {res}; "
        if COMMIT_EVERY and i % COMMIT_EVERY == 0:
            git_checkpoint(f"ВСН: файлы до №{i} из {len(docs)}")

    fields = ["id", "number", "name", "date", "status", "pdf_path", "htm_path",
              "pdf_url", "htm_url", "card_url", "note"]
    with open(ROOT / "index.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter=";")
        w.writeheader()
        w.writerows(docs)
    with open(ROOT / "remaining.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter=";")
        w.writeheader()
        w.writerows(remaining)

    def link(p, label):
        return f"[{label}]({urllib.parse.quote(p)})" if p else ""

    lines = [
        "# ВСН — Ведомственные строительные нормы",
        "",
        f"Источник: <{LIST_URLS[0]}>. Документов в списке: **{len(docs)}**. "
        f"Не поместилось в репозиторий: **{len(remaining)}** (см. `remaining.csv`).",
        "",
        "Полный реестр с путями — `index.csv` (разделитель `;`, открывается в Excel).",
        "",
        "| № | Номер | Название | Дата введения | Статус | Файлы |",
        "|---|---|---|---|---|---|",
    ]
    for n, d in enumerate(docs, 1):
        files = " ".join(filter(None, [link(d["pdf_path"], "PDF"), link(d["htm_path"], "HTM")]))
        name = d["name"].replace("|", "/")
        lines.append(f"| {n} | {d['number']} | {name} | {d['date']} | {d['status']} | {files or '—'} |")
    (ROOT / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Итог:", stats, "| объём files/, МБ:", round(dir_size_mb(FILES_DIR), 1), flush=True)


if __name__ == "__main__":
    main()
