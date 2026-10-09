#!/usr/bin/env python3
"""Парсер anteikutaern.at.ua -> data/<раздел>.js для Broken Ranks Wiki.

Запуск из корня репозитория:
    pip install -r scraper/requirements.txt
    python scraper/scrape.py                 # все разделы
    python scraper/scrape.py mobs pets       # только указанные
    python scraper/scrape.py --no-images     # без скачивания иконок
    python scraper/scrape.py --offline       # только из кэша scraper/cache

Все скачанные страницы кэшируются в scraper/cache/, поэтому повторный запуск
(например, после доработки разбора) не нагружает сайт.

Разметку сайта автор парсера не видел (сайт был недоступен при написании),
поэтому разбор эвристический: таблицы со строками-записями, блоки материалов
uCoz и страницы отдельных записей вида «Параметр: значение».
"""

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag

import requests
from bs4 import BeautifulSoup, NavigableString, Tag

BASE = os.environ.get("BR_BASE", "https://anteikutaern.at.ua")
ROOT = Path(__file__).resolve().parent.parent
CACHE = Path(os.environ.get("BR_CACHE_DIR", Path(__file__).resolve().parent / "cache"))
DATA = Path(os.environ.get("BR_DATA_DIR", ROOT / "data"))

# start: (категория или None, путь). Если категория None и split=True,
# категориями становятся подстраницы раздела (шлемы, оружие и т.п.).
SECTIONS = {
    "equipment": {"starts": [(None, "/dropdir/")], "split": True},
    "pets": {"starts": [(None, "/pety/")], "split": False},
    "mobs": {
        "starts": [
            ("normal", "/mobs/mobs/"),
            ("bosses", "/mobs/bosses/"),
            ("champions", "/mobs/champions/"),
        ],
        "split": False,
    },
    "items": {"starts": [(None, "/items/")], "split": True},
    "npc": {"starts": [(None, "/others/npc/")], "split": False},
}

CONTENT_SELECTORS = [
    "#allEntries", "#content", ".content", "#main", ".main", "td.main",
    "#centerBlock", ".eMessage", "article", "#site-content",
]
SKIP_LINK_RE = re.compile(r"(/index/|/register|/login|/search|/forum|/gb/|/stat/|\?|#|mailto:|javascript:)", re.I)
IMG_SKIP_RE = re.compile(r"(spacer|blank|pixel|counter|banner|/ucoz/|/img/icon/|smile|rating|\.gif$)", re.I)
LABEL_RE = re.compile(r"^\s*([^:\n]{1,48}?)\s*[:：]\s*(.+?)\s*$")
LEVEL_RE = re.compile(r"^(уровень|ур\.?|lvl|level)(\s|$)", re.I)

session = requests.Session()
session.headers["User-Agent"] = "Mozilla/5.0 (personal wiki mirror; BrokenRanksWiki scraper)"
args = None


# ---------- загрузка ----------

def fetch(url):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".html")
    if path.exists():
        return path.read_text("utf-8", errors="replace")
    if args.offline:
        return None
    for attempt in range(4):
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            r.encoding = r.apparent_encoding if r.encoding in (None, "ISO-8859-1") else r.encoding
            html = r.text
            path.write_text(html, "utf-8")
            (CACHE / "index.tsv").open("a", encoding="utf-8").write(f"{path.name}\t{url}\n")
            time.sleep(args.delay)
            return html
        except requests.RequestException as e:
            print(f"  ! {url}: {e}", file=sys.stderr)
            time.sleep(2 ** attempt)
    return None


def soup_of(url):
    html = fetch(url)
    return BeautifulSoup(html, "html.parser") if html else None


def download_icon(src, section):
    if not src:
        return ""
    if args.no_images:
        return src
    ext = Path(urlparse(src).path).suffix.lower()
    if ext not in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg"):
        ext = ".png"
    rel = Path("img") / section / (hashlib.sha1(src.encode()).hexdigest()[:16] + ext)
    out = DATA / rel
    if not out.exists():
        if args.offline:
            return src
        try:
            r = session.get(src, timeout=30)
            r.raise_for_status()
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(r.content)
            time.sleep(args.delay / 2)
        except requests.RequestException as e:
            print(f"  ! icon {src}: {e}", file=sys.stderr)
            return src
    return "data/" + rel.as_posix()


# ---------- утилиты разбора ----------

def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def content_root(soup):
    for sel in CONTENT_SELECTORS:
        node = soup.select_one(sel)
        if node and len(node.get_text(strip=True)) > 50:
            return node
    return soup.body or soup


def internal(url):
    p = urlparse(url)
    return p.netloc in ("", urlparse(BASE).netloc, "www." + urlparse(BASE).netloc)


def abs_url(href, page_url):
    return urldefrag(urljoin(page_url, href))[0]


def good_img(img, page_url):
    src = img.get("data-src") or img.get("src") or ""
    if not src or IMG_SKIP_RE.search(src):
        return None
    try:
        w = int(img.get("width") or 999)
        if w < 12:
            return None
    except ValueError:
        pass
    return abs_url(src, page_url)


def lines_of(node):
    """Текст узла, разбитый по <br>, блочным тегам и переводам строк."""
    parts, buf = [], []

    def walk(n):
        for ch in n.children:
            if isinstance(ch, NavigableString):
                buf.append(str(ch))
            elif isinstance(ch, Tag):
                if ch.name in ("script", "style"):
                    continue
                block = ch.name in ("br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "table", "ul", "ol")
                if block:
                    parts.append("".join(buf)); buf.clear()
                walk(ch)
                if block:
                    parts.append("".join(buf)); buf.clear()
    walk(node)
    parts.append("".join(buf))
    out = []
    for p in parts:
        out.extend(clean(x) for x in p.split("\n"))
    return [x for x in out if x]


def split_fields(lines):
    fields, rest = [], []
    for ln in lines:
        m = LABEL_RE.match(ln)
        if m and not m.group(1).startswith("http"):
            fields.append([clean(m.group(1)), clean(m.group(2))])
        else:
            rest.append(ln)
    return fields, rest


def level_of(fields):
    for k, v in fields:
        if LEVEL_RE.match(k):
            m = re.search(r"\d+", v)
            if m:
                return int(m.group())
    return None


def slug(text):
    tr = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюя",
                  ["a", "b", "v", "g", "d", "e", "e", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r",
                   "s", "t", "u", "f", "h", "c", "ch", "sh", "sch", "", "y", "", "e", "yu", "ya"]))
    s = "".join(tr.get(c, c) for c in text.lower())
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "x"


# ---------- извлечение записей ----------

def entries_from_tables(root, page_url):
    found = []
    for table in root.find_all("table"):
        if table.find("table"):  # таблица-раскладка, разбираем вложенные
            continue
        rows = table.find_all("tr")
        if len(rows) < 1:
            continue
        header = None
        first = rows[0]
        if first.find("th") or (not first.find("img") and len(rows) > 1 and len(first.find_all(["td", "th"])) > 1):
            header = [clean(c.get_text(" ")) for c in first.find_all(["td", "th"])]
            rows = rows[1:]
        for tr in rows:
            cells = tr.find_all(["td", "th"])
            img = next((u for u in (good_img(i, page_url) for i in tr.find_all("img")) if u), None)
            if not img or not cells:
                continue
            e = entry_from_cells(cells, header, img, page_url)
            if e:
                found.append(e)
    return found


def entry_from_cells(cells, header, img, page_url):
    link = None
    for a in cells[0].find_parent("tr").find_all("a", href=True):
        u = abs_url(a["href"], page_url)
        if internal(u) and not SKIP_LINK_RE.search(urlparse(u).path + ("?" if urlparse(u).query else "")):
            link = u
            break
    name = ""
    for c in cells:
        cand = c.find(["b", "strong", "a", "h3", "h4"])
        name = clean(cand.get_text(" ")) if cand else ""
        if name:
            break
    if not name:
        im = cells[0].find_parent("tr").find("img")
        name = clean(im.get("alt") or im.get("title") or "") if im else ""
    fields, desc = [], []
    for i, c in enumerate(cells):
        lines = lines_of(c)
        if not lines:
            continue
        if not name:
            name = lines[0]
        if lines and lines[0] == name:
            lines = lines[1:]
        f, rest = split_fields(lines)
        fields += f
        label = header[i] if header and i < len(header) else ""
        if rest:
            if label and label.lower() not in ("", "иконка", "картинка", "изображение", "фото", "название", "имя"):
                fields.append([label, "; ".join(rest)])
            else:
                desc += rest
    if not name:
        return None
    return {"name": name, "img": img, "fields": fields, "description": "\n".join(desc), "link": link}


def entries_from_blocks(root, page_url):
    """Материалы uCoz (модули load/publ/blog): div.eBlock / table.eBlock и т.п."""
    found = []
    for blk in root.select(".eBlock, .entry, .material, .catalog-item, .item-block"):
        title = blk.select_one(".eTitle, .entry-title, h2, h3")
        if not title:
            continue
        name = clean(title.get_text(" "))
        a = title.find("a", href=True)
        link = abs_url(a["href"], page_url) if a else None
        img = next((u for u in (good_img(i, page_url) for i in blk.find_all("img")) if u), None)
        body = blk.select_one(".eMessage, .eText, .entry-content") or blk
        lines = [ln for ln in lines_of(body) if ln != name]
        fields, rest = split_fields(lines)
        found.append({"name": name, "img": img, "fields": fields, "description": "\n".join(rest), "link": link})
    return found


def detail_page(url):
    """Страница отдельной записи: иконка, «Параметр: значение», описание, списки (дроп и т.п.)."""
    soup = soup_of(url)
    if not soup:
        return {}
    root = content_root(soup)
    h = root.find(["h1", "h2"]) or soup.find("h1")
    img = next((u for u in (good_img(i, url) for i in root.find_all("img")) if u), None)
    lists = []
    for ul in root.find_all(["ul", "ol"]):
        items = [clean(li.get_text(" ")) for li in ul.find_all("li", recursive=False)]
        items = [x for x in items if x]
        if not items:
            continue
        prev = ul.find_previous(["b", "strong", "h3", "h4", "p"])
        title = clean(prev.get_text(" ")).rstrip(":") if prev else "Список"
        lists.append({"title": title[:60] or "Список", "items": items})
        ul.decompose()  # чтобы элементы списка не дублировались в описании
    lines = lines_of(root)
    fields, rest = split_fields(lines)
    name = clean(h.get_text(" ")) if h else ""
    rest = [x for x in rest if x != name]
    return {"name": name, "img": img, "fields": fields, "description": "\n".join(rest[:40]), "lists": lists}


# ---------- обход раздела ----------

def subpages(root, page_url, start_path):
    """Ссылки на страницы внутри раздела (подкатегории и пагинация)."""
    out = []
    for a in root.find_all("a", href=True):
        u = abs_url(a["href"], page_url)
        p = urlparse(u)
        if not internal(u) or SKIP_LINK_RE.search(p.path):
            continue
        if p.path.startswith(start_path) and p.path.rstrip("/") != start_path.rstrip("/"):
            out.append((clean(a.get_text(" ")), u))
    return out


def is_pagination(text, url):
    return bool(re.fullmatch(r"\d+|»|«|>|<|след.*|пред.*|далее|назад", text.lower())) or \
        bool(re.search(r"/\d+/?$|-\d+$|page\d+", urlparse(url).path))


def scrape_section(sid, conf):
    print(f"== {sid}")
    categories, entries, seen = {}, [], set()

    def collect(category, url, depth, visited):
        if url in visited or depth > args.depth:
            return
        visited.add(url)
        soup = soup_of(url)
        if not soup:
            return
        root = content_root(soup)
        raw = entries_from_tables(root, url) + entries_from_blocks(root, url)
        print(f"  {url}  [{category}]  -> {len(raw)}")
        for r in raw:
            add_entry(category, r, url)
        start_path = urlparse(url).path
        for text, sub in subpages(root, url, start_path):
            if sub in visited:
                continue
            if is_pagination(text, sub):
                collect(category, sub, depth, visited)
            elif depth == 0 and conf["split"] and category_from_start is None:
                cid = slug(urlparse(sub).path.rstrip("/").rsplit("/", 1)[-1] or text)
                categories.setdefault(cid, {"id": cid, "name": text or cid, "source": sub})
                collect(cid, sub, depth + 1, visited)
            elif not raw:
                # страница-оглавление без записей: идём глубже, но в той же категории
                collect(category, sub, depth + 1, visited)

    def add_entry(category, r, page_url):
        if args.details and r.get("link") and r["link"] != page_url:
            d = detail_page(r["link"])
            known = {k for k, _ in r["fields"]}
            r["fields"] += [f for f in d.get("fields", []) if f[0] not in known]
            r["img"] = r["img"] or d.get("img")
            if not r["description"]:
                r["description"] = d.get("description", "")
            r["lists"] = d.get("lists", [])
        cat = category or "_"
        if sid == "mobs" and cat == "normal":
            text = " ".join([r["name"], r["description"]] + [v for f in r["fields"] for v in f]).lower()
            if "элит" in text:
                cat = "elite"
        key = (cat, r["name"].lower())
        if key in seen:
            return
        seen.add(key)
        entries.append({
            "id": f"{sid}/{cat}/{slug(r['name'])}",
            "category": cat,
            "name": r["name"],
            "icon": download_icon(r.get("img"), sid),
            "level": level_of(r["fields"]),
            "fields": r["fields"],
            "description": r["description"],
            "lists": r.get("lists", []),
            "sourceUrl": r.get("link") or page_url,
        })

    for category_from_start, path in conf["starts"]:
        collect(category_from_start, BASE + path, 0, set())

    # Уникальность id
    ids = {}
    for e in entries:
        n = ids.get(e["id"], 0)
        ids[e["id"]] = n + 1
        if n:
            e["id"] += f"-{n + 1}"

    data = {"updated": date.today().isoformat(), "categories": list(categories.values()), "entries": entries}
    DATA.mkdir(exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=1)
    (DATA / f"{sid}.json").write_text(payload, "utf-8")
    (DATA / f"{sid}.js").write_text(
        f"(window.BR_DATA = window.BR_DATA || {{}})[{json.dumps(sid)}] = {payload};\n", "utf-8")
    print(f"  => {len(entries)} записей, {len(categories)} категорий")


def main():
    global args
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sections", nargs="*", help=f"разделы: {', '.join(SECTIONS)} (по умолчанию все)")
    ap.add_argument("--no-images", action="store_true", help="не скачивать иконки (оставить ссылки на сайт)")
    ap.add_argument("--no-details", dest="details", action="store_false", help="не заходить на страницы записей")
    ap.add_argument("--offline", action="store_true", help="не ходить в сеть, только кэш")
    ap.add_argument("--delay", type=float, default=0.7, help="пауза между запросами, сек")
    ap.add_argument("--depth", type=int, default=2, help="глубина обхода подстраниц")
    args = ap.parse_args()
    unknown = set(args.sections) - set(SECTIONS)
    if unknown:
        ap.error(f"неизвестные разделы: {', '.join(sorted(unknown))}")
    for sid in args.sections or SECTIONS:
        scrape_section(sid, SECTIONS[sid])


if __name__ == "__main__":
    main()
