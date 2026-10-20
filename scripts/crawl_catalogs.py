#!/usr/bin/env python3
"""Сбор каталогов ВСН со всех баз meganorm.ru / files.stroyinf.ru (для анализа недостающих).

Источники:
  meganorm.ru/list0|1|2.htm            — базы 1–3: категории «ВСН*», страницы <id>-N.htm
  meganorm.ru/mega_doc/.../vsn_*       — раздел «Актуальные документы → ВСН»
  files.stroyinf.ru/list0|1|2.htm      — зеркало баз
Результат: catalogs/sources.csv (источник; номер; название; дата; статус; ссылки)
"""
import csv
import html
import re
import sys
import time
import urllib.parse
from pathlib import Path

import requests

S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0 Safari/537.36",
                  "Accept-Language": "ru-RU,ru;q=0.9"})
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "catalogs")
OUT.mkdir(exist_ok=True)
seen_pages = set()


DBG = OUT / "debug"
DBG.mkdir(exist_ok=True)
LOG = open(OUT / "crawl_log.txt", "w", encoding="utf-8")
_print = print


def print(*a, **k):  # noqa: A001
    _print(*a, **k)
    LOG.write(" ".join(map(str, a)) + "\n")
    LOG.flush()


def save_debug(url, h):
    name = re.sub(r"[^\w.-]+", "_", url.split("//", 1)[-1])[:120]
    (DBG / name).write_text(h[:300000], encoding="utf-8")


def get(url):
    for i in range(3):
        try:
            r = S.get(url, timeout=60)
            if r.status_code == 200:
                for enc in ("utf-8", "cp1251"):
                    try:
                        return r.content.decode(enc)
                    except UnicodeDecodeError:
                        pass
                return r.content.decode("cp1251", "replace")
            if r.status_code == 404:
                return None
            print("HTTP", r.status_code, url, flush=True)
        except requests.RequestException as e:
            print("ERR", e, url, flush=True)
        time.sleep(3 * (i + 1))
    return None


def txt(s):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", s)).split())


def parse_table(page_html, base_url, source):
    rows = []
    for tr in re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", page_html):
        tds = re.findall(r"(?is)<td[^>]*>(.*?)</td>", tr)
        if len(tds) < 2:
            continue
        links = [urllib.parse.urljoin(base_url, h) for h in re.findall(r'(?i)href="([^"]+)"', tds[0] + tds[1])]
        anchors = [txt(a) for a in re.findall(r"(?is)<a[^>]*>(.*?)</a>", tds[0])]
        number = next((a for a in reversed(anchors) if re.match(r"(?i)(ВСН|ВНЭ|BCH)", a)), "") or txt(tds[0])
        if not re.search(r"(?i)\bВСН|ВНЭ", number + " " + txt(tds[1])[:30]):
            continue
        rows.append({
            "source": source, "number": number, "name": txt(tds[1]),
            "date": txt(tds[2]) if len(tds) > 2 else "", "status": txt(tds[3]) if len(tds) > 3 else "",
            "links": " ".join(l for l in links if re.search(r"/Data\d|/Index\d|mega_doc|\.pdf", l)),
        })
    return rows


def crawl_category(first_url, source):
    rows, queue = [], [first_url]
    m = re.match(r"(.*/)(\d+)-\d+\.htm$", first_url)
    while queue:
        u = queue.pop(0)
        if u in seen_pages:
            continue
        seen_pages.add(u)
        h = get(u)
        time.sleep(1)
        if not h:
            continue
        rows += parse_table(h, u, source)
        if m:  # пагинация вида <cat>-N.htm
            for p in set(re.findall(rf'href="([^"]*?/?{m.group(2)}-\d+\.htm)"', h)):
                queue.append(urllib.parse.urljoin(u, p))
    print(f"{source}: {first_url} -> {len(rows)}", flush=True)
    return rows


def crawl_base(root, list_name):
    h = get(f"{root}/{list_name}.htm")
    print("base", root, list_name, "len", len(h) if h else None)
    if not h:
        return []
    save_debug(f"{root}/{list_name}.htm", h)
    rows = []
    for href, label in re.findall(r'(?is)<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', h):
        label = txt(label)
        if re.match(r"(?i)^(ВСН|ВНЭ)\b", label) and re.search(r"\d+-0\.htm$", href):
            rows += crawl_category(urllib.parse.urljoin(f"{root}/{list_name}.htm", href), f"{root.split('//')[1]}/{list_name}:{label}")
    return rows


def crawl_megadoc():
    base = "https://meganorm.ru/mega_doc/norm/vsn_vedomstvennye-stroitelnye-normy/"
    rows, queue = [], [base + "vsn_vedomstvennye-stroitelnye-normy_0.html"]
    while queue:
        u = queue.pop(0)
        if u in seen_pages:
            continue
        seen_pages.add(u)
        h = get(u)
        time.sleep(1)
        print("mega_doc page", u, "len", len(h) if h else None)
        if not h:
            continue
        save_debug(u, h)
        before = len(rows)
        for a_href, a_txt in re.findall(r'(?is)<a[^>]+href="([^"]*/vsn_vedomstvennye-stroitelnye-normy/\d+/[^"]+\.html)"[^>]*>(.*?)</a>', h):
            t = txt(a_txt)
            if t:
                rows.append({"source": "meganorm.ru/mega_doc", "number": t.split(" ")[0] + (" " + t.split(" ")[1] if len(t.split(" ")) > 1 else ""),
                             "name": t, "date": "", "status": "", "links": urllib.parse.urljoin(u, a_href)})
        rows += [dict(r, source="meganorm.ru/mega_doc") for r in parse_table(h, u, "meganorm.ru/mega_doc")]
        for p in set(re.findall(r'href="([^"]*vsn_vedomstvennye-stroitelnye-normy_\d+\.html)"', h)):
            queue.append(urllib.parse.urljoin(u, p))
        print("mega_doc", u, len(rows) - before, flush=True)
    return rows


def main():
    rows = []
    for root in ("https://meganorm.ru", "https://files.stroyinf.ru"):
        for ln in ("list0", "list1", "list2", "list3"):
            rows += crawl_base(root, ln)
    rows += crawl_megadoc()
    with open(OUT / "sources.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["source", "number", "name", "date", "status", "links"], delimiter=";")
        w.writeheader()
        w.writerows(rows)
    print("Итого строк:", len(rows))


if __name__ == "__main__":
    main()
