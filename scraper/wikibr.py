#!/usr/bin/env python3
"""Разбор копии wikibr.pl (scraper/mirror/wikibr.pl) в данные для нашей вики.

    python scraper/wikibr.py        # вызывается и из build.py

Результат — scraper/source/wikibr.json:
    {"pages": {<название>: {"kind", "title", "image", "blocks": [{"title", "html"}], "links": [...]}},
     "images": [<пути картинок на wikibr.pl>]}

Статьи разбираются по таблицам: строки-заголовки («Zastosowanie», «Jak zdobyć?»…)
становятся заголовками блоков, строки под ними — содержимым. Гайды и прочие
статьи без такой таблицы сохраняются целиком.
"""

import gzip
import json
import re
from pathlib import Path
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

HERE = Path(__file__).resolve().parent
MIRROR = HERE / "mirror" / "wikibr.pl"
OUT = HERE / "source" / "wikibr.json"

SKIP_TITLES = {"Strona główna", "Zgłoś błąd", "Test D", "Test lista", "Szablon", "Itemki roboczo"}

# Перевод частых заголовков; содержимое остаётся польским.
HEADERS = {
    "statystyki": "Статистика", "strefy ataku": "Зоны атаки", "umiejętności": "Умения",
    "odporności / umiejętności specjalne": "Иммунитеты / особые умения", "drużyna": "Команда",
    "lokalizacja": "Локация", "drop": "Дроп", "zastosowanie": "Применение", "jak zdobyć?": "Как добыть",
    "używa": "Использует", "dodatkowe informacje": "Доп. информация", "opis": "Описание",
    "inne:": "Прочее", "inne": "Прочее", "nagroda": "Награда", "nagrody": "Награды", "wymagania": "Требования",
    "ścieżka": "Путь", "aspekt": "Аспект", "oznaczenia na mapie": "Обозначения на карте",
    "jak dotrzeć na instancję": "Как попасть в инстанс", "przeciwnicy": "Противники", "mapa": "Карта",
}


def kind_of(title, s):
    if "Oznaczenia na mapie" in s:
        return "location"
    if "Jak dotrzeć na instancję" in s:
        return "instance"
    if "Rodzaj akcji" in s and "Strefa akcji" in s:
        return "class"
    if title != "Nasycenie" and "Ścieżka" in s and "Aspekt" in s:
        return "champion"
    if "Punkty życia" in s and ("Strefy ataku" in s or "Drop" in s):
        return "mob"
    if "Używa" in s and "Statystyki" in s:
        return "pet"
    if ("Wartość" in s and "Waga" in s) or "Jak zdobyć" in s or "Zastosowanie" in s:
        return "item"
    return "guide"


def page_title_from_href(href):
    """'/index.php/Wielka_Flasza_Si%C5%82y' -> 'Wielka Flasza Siły'; красные ссылки -> None."""
    if not href or "redlink=1" in href:
        return None
    p = urlparse(href)
    if p.netloc and "wikibr" not in p.netloc:
        return None
    m = re.match(r"/index\.php/(.+)", p.path)
    if m:
        t = unquote(m.group(1)).replace("_", " ")
    else:
        q = dict(x.split("=", 1) for x in p.query.split("&") if "=" in x)
        t = unquote(q.get("title", "")).replace("_", " ")
    if not t or re.match(r"(Plik|Specjalna|Kategoria|Szablon|Użytkownik):", t):
        return None
    return t


class Cleaner:
    """Чистит HTML статьи: оставляет простые теги, ссылки на статьи помечает data-wikibr,
    картинки — data-wikibr-img (путь на wikibr.pl)."""

    ALLOWED = {"b", "strong", "i", "em", "br", "p", "ul", "ol", "li", "table", "tr", "td", "th", "tbody",
               "thead", "span", "div", "img", "h2", "h3", "h4", "hr", "sup", "small", "center", "dl", "dt", "dd"}

    def __init__(self):
        self.images = set()
        self.links = set()

    def __call__(self, node):
        soup = BeautifulSoup(str(node), "html.parser")
        for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
            c.extract()
        for t in soup.select("style, script, .mw-editsection, .reference, .mw-references-wrap, .toc, #toc, .mw-collapsible-toggle"):
            t.decompose()
        for t in list(soup.find_all(True)):
            if t.name == "a":
                title = page_title_from_href(t.get("href"))
                if title and t.find("img") is None:
                    self.links.add(title)
                    t.name = "span"
                    t.attrs = {"data-wikibr": title}
                else:
                    if t.find("img") is not None and title:
                        for im in t.find_all("img"):
                            im["data-wikibr"] = title
                        self.links.add(title)
                    t.unwrap()
                continue
            if t.name not in self.ALLOWED:
                t.unwrap()
                continue
            attrs = {}
            if t.name == "img":
                src = t.get("src", "")
                if src.startswith("/images/thumb/"):
                    # /images/thumb/a/ab/X.png/40px-X.png -> оригинал /images/a/ab/X.png
                    src = re.sub(r"^/images/thumb/(.+?)/[^/]+$", r"/images/\1", src)
                if src.startswith("/images/"):
                    self.images.add(src)
                    attrs["data-wikibr-img"] = src
                else:
                    t.decompose()
                    continue
                for a in ("alt", "data-wikibr"):
                    if t.get(a):
                        attrs["title" if a == "alt" else a] = t[a]
            elif t.name in ("td", "th"):
                for a in ("colspan", "rowspan"):
                    if t.get(a) and t[a] != "1":
                        attrs[a] = t[a]
            else:
                style = t.get("style", "")
                m = re.search(r"(?<![-\w])color\s*:\s*(#[0-9a-fA-F]{3,8}|[a-z]+)", style)
                if m and t.name == "span":
                    attrs["style"] = f"color:{m.group(1)}"
            t.attrs = attrs
        html = str(soup)
        html = re.sub(r"\s*\n\s*", " ", html)
        html = re.sub(r"(<br/?>\s*){3,}", "<br><br>", html)
        return html.strip()


def text(node):
    return re.sub(r"\s+", " ", node.get_text(" ")).strip()


def is_header_cell(td):
    """Ячейка-заголовок: <th> или ячейка, весь текст которой — короткий жирный текст."""
    if td.name == "th":
        return bool(text(td))
    t = text(td)
    if not t or len(t) > 45 or td.find("img"):
        return False
    bold = " ".join(text(b) for b in td.find_all(["b", "strong"]))
    return bold.strip() == t


def inner(html):
    return re.sub(r"^<t[dh][^>]*>|</t[dh]>$", "", html.strip()).strip()


def top_tables(content):
    """Таблицы верхнего уровня (в том числе обёрнутые в <center>/<div>)."""
    return [t for t in content.find_all("table") if not t.find_parent("table")]


def parse_table(table, clean, page_title, prefix=""):
    """Разбор «карточки» в таблице: заголовок -> блок, пары заголовков -> поля."""
    blocks, fields = [], []
    rows = [r for r in table.find_all("tr") if r.find_parent("table") is table]
    cur_title, cur_rows = None, []

    def flush():
        nonlocal cur_title, cur_rows
        body = "".join(cur_rows)
        if body and (re.sub(r"<[^>]+>", "", body).strip() or "<img" in body):
            title = cur_title if cur_title and cur_title != page_title else "Описание"
            blocks.append({"title": (prefix + title) if prefix else title,
                           "html": f'<table class="wb">{body}</table>'})
        cur_title, cur_rows = None, []

    i = 0
    while i < len(rows):
        cells = rows[i].find_all(["td", "th"], recursive=False)
        nonempty = [c for c in cells if text(c) or c.find("img")]
        if i == 0 and any(c.find("img") for c in cells) and len(text(rows[i])) < 80:
            i += 1  # первая строка — картинка и название записи
            continue
        if nonempty and all(is_header_cell(c) for c in nonempty):
            nxt = rows[i + 1].find_all(["td", "th"], recursive=False) if i + 1 < len(rows) else []
            if len(nonempty) >= 2 and len(nxt) == len(cells) and not all(is_header_cell(c) for c in nxt if text(c)):
                for h, v in zip(cells, nxt):
                    if text(h) and (text(v) or v.find("img")):
                        fields.append([prefix + text(h), inner(clean(v)) if v.find(["img", "a", "p", "br"]) else text(v)])
                i += 2
                continue
            flush()
            cur_title = " / ".join(text(c) for c in nonempty)
            i += 1
            continue
        if nonempty:
            cur_rows.append("<tr>" + "".join(clean(c) for c in cells) + "</tr>")
        i += 1
    flush()
    return fields, blocks


def parse_table_page(content, clean, page_title):
    tables = top_tables(content)
    fields, blocks = [], []
    for n, table in enumerate(tables):
        prefix = ""
        if n:
            # Вторая и следующие таблицы — обычно другие версии (путь вызова и т.п.).
            head = re.sub(r"\s*\[\d+\]", "", text(table.find("tr")) if table.find("tr") else "").strip()
            prefix = (head[:40] + ": ") if head and head != page_title else f"Вариант {n + 1}: "
        f, b = parse_table(table, clean, page_title, prefix)
        fields += f
        blocks += b
    # Текст вне таблиц (сноски, пояснения).
    after = []
    for el in content.children:
        if isinstance(el, Tag) and not el.find("table") and el.name != "table" and text(el):
            html = clean(el)
            if re.sub(r"<[^>]+>", "", html).strip():
                after.append(html)
    if after:
        blocks.append({"title": "Примечания", "html": " ".join(after)})
    return fields, blocks


def main_image(content, title):
    imgs = [im for im in content.find_all("img") if im.get("src", "").startswith("/images/")]
    def orig(im):
        return re.sub(r"^/images/thumb/(.+?)/[^/]+$", r"/images/\1", im["src"])
    for im in imgs:
        if (im.get("alt") or "").strip().lower() == title.lower():
            return orig(im)
    # иначе — самая крупная картинка (иконки короны, звёзд и т.п. маленькие)
    def area(im):
        try:
            return int(im.get("width") or 0) * int(im.get("height") or 0)
        except ValueError:
            return 0
    imgs.sort(key=area, reverse=True)
    return orig(imgs[0]) if imgs else None


def translate(title):
    return HEADERS.get(title.strip().lower(), title)


def main():
    rows = {}
    for line in (MIRROR / "pages.tsv").read_text("utf-8").splitlines():
        parts = line.split("\t")
        if len(parts) >= 4:
            t = re.sub(r"\s+[–-]\s+Wiki BR$", "", parts[3]).strip()
            rows[t] = parts[1]
    wikitext = {}
    for line in gzip.open(MIRROR / "mediawiki" / "wikitext.jsonl.gz", "rt", encoding="utf-8"):
        r = json.loads(line)
        wikitext[r["title"]] = r
    pages, images = {}, set()
    for title, r in wikitext.items():
        if title in SKIP_TITLES or title not in rows:
            continue
        wt = r["wikitext"]
        m = re.match(r"\s*#(PATRZ|REDIRECT|PRZEKIERUJ)\s*\[\[([^\]|]+)", wt, re.I)
        if m:
            pages[title] = {"kind": "redirect", "title": title, "target": m.group(2).strip()}
            continue
        soup = BeautifulSoup(gzip.open(MIRROR / "pages" / f"{rows[title]}.html.gz").read(), "html.parser")
        content = soup.select_one(".mw-parser-output") or soup.select_one("#mw-content-text")
        if not content:
            continue
        kind = kind_of(title, wt)
        clean = Cleaner()
        main_img = main_image(content, title)
        if kind in ("guide", "location", "instance", "class"):
            fields, blocks = [], [{"title": "Статья", "html": clean(content)}]
        else:
            fields, blocks = parse_table_page(content, clean, title)
        for b in blocks:
            pre, _, rest = b["title"].rpartition(": ")
            b["title"] = (pre + ": " if pre else "") + translate(rest)
        for f in fields:
            pre, _, rest = f[0].rpartition(": ")
            f[0] = (pre + ": " if pre else "") + translate(rest)
        # Блок «Описание», где нет ничего, кроме картинки записи, не нужен.
        def meaningful(b):
            t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", b["html"])).strip()
            if t and t != title:
                return True
            return b["html"].count("<img") > 1 or bool(main_img and main_img not in b["html"])
        blocks = [b for b in blocks if meaningful(b)]
        if main_img:
            clean.images.add(main_img)
        images |= clean.images
        pages[title] = {"kind": kind, "title": title, "image": main_img, "fields": fields, "blocks": blocks,
                        "links": sorted(clean.links)}
    OUT.write_text(json.dumps({"pages": pages, "images": sorted(images)}, ensure_ascii=False, indent=1), "utf-8")
    kinds = {}
    for p in pages.values():
        kinds[p["kind"]] = kinds.get(p["kind"], 0) + 1
    print(f"wikibr: {len(pages)} статей {kinds}, картинок: {len(images)}")


if __name__ == "__main__":
    main()
