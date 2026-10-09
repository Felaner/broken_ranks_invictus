#!/usr/bin/env python3
"""Сохраняет копию сайта-вики (по умолчанию wikibr.pl) для последующего разбора.

Открывает сайт в настоящем браузере (как recon.py), обходит все внутренние
страницы и сохраняет:

    scraper/mirror/<host>/pages/<hash>.html.gz   — HTML каждой страницы после отрисовки
    scraper/mirror/<host>/pages.tsv              — url, файл, заголовок
    scraper/mirror/<host>/responses/...          — JSON/AJAX-ответы сервера (сжатые)
    scraper/mirror/<host>/shots/*.jpg            — скриншоты первых страниц
    scraper/mirror/<host>/mediawiki/*.json       — если это MediaWiki: сведения о сайте и список страниц

Обход можно прервать (Ctrl+C) и продолжить тем же запуском — уже сохранённые
страницы не скачиваются повторно.

Запуск из корня репозитория:
    python scraper/mirror.py --browser firefox
    python scraper/mirror.py --browser firefox --max-pages 50    # сначала пробно
    python scraper/mirror.py https://другой-сайт/ --browser firefox
"""

import argparse
import gzip
import hashlib
import json
import random
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag, parse_qs, unquote

from playwright.sync_api import sync_playwright, Error as PWError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from recon import add_browser_args, launch_browser  # noqa: E402

TEXT_TYPES = re.compile(r"(json|xml|text/plain)", re.I)
SKIP_EXT = re.compile(r"\.(png|jpe?g|gif|webp|svg|ico|bmp|mp4|webm|mp3|ogg|zip|rar|7z|pdf|css|js|woff2?|ttf)$", re.I)
# Служебные страницы MediaWiki и подобных движков: правки, история, сравнения версий…
SKIP_QUERY = {"action", "oldid", "diff", "curid", "printable", "veaction", "redlink", "returnto", "uselang",
              "mobileaction", "useskin", "limit", "offset", "from", "until", "dir"}
SKIP_PATH = re.compile(r"(Special|Specjalna|Specjalne|Служебная|Talk|Dyskusja|User|Użytkownik|"
                       r"MediaWiki|Template_talk|File_talk|Szablon_dyskusja)(_talk)?:", re.I)
KEEP_SPECIAL = re.compile(r"(AllPages|Wszystkie_strony|Categories|Kategorie)", re.I)

LINKS_JS = "() => [...document.querySelectorAll('a[href]')].map(a => a.href)"


def h(s):
    return hashlib.sha1(s.encode()).hexdigest()[:16]


def norm_url(url, host):
    url = urldefrag(url)[0]
    p = urlparse(url)
    if p.scheme not in ("http", "https") or p.netloc.lower().removeprefix("www.") != host:
        return None
    if SKIP_EXT.search(p.path):
        return None
    path = unquote(p.path)
    if SKIP_PATH.search(path) and not KEEP_SPECIAL.search(path):
        return None
    if p.query:
        q = parse_qs(p.query)
        if set(q) & SKIP_QUERY:
            # Пагинация списков (Специальная:Все страницы?from=…) нужна, остальное — нет.
            if not (KEEP_SPECIAL.search(url) and set(q) <= {"from", "title", "namespace", "pagefrom", "hideredirects"}):
                return None
        title = q.get("title", [""])[0]
        if title and SKIP_PATH.search(title + ":") and not KEEP_SPECIAL.search(title):
            return None
    return p._replace(netloc=p.netloc.lower()).geturl()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("start", nargs="?", default="https://www.wikibr.pl/", help="адрес сайта")
    add_browser_args(ap)
    ap.add_argument("--max-pages", type=int, default=6000, help="максимум страниц за всё время")
    ap.add_argument("--full", dest="api_only", action="store_false",
                    help="MediaWiki: обходить все страницы, а не только выборку (данные и так берутся через API)")
    ap.add_argument("--sample", type=int, default=150, help="MediaWiki: сколько страниц сохранить как образцы вёрстки")
    ap.add_argument("--shots", type=int, default=25, help="сколько первых страниц сфотографировать")
    ap.add_argument("--delay", type=float, default=0.3, help="пауза между страницами, сек")
    ap.add_argument("--wait", type=int, default=600, help="ожидание отрисовки страницы, мс")
    args = ap.parse_args()

    start = args.start if "://" in args.start else "https://" + args.start
    host = urlparse(start).netloc.lower().removeprefix("www.")
    out = Path(__file__).resolve().parent / "mirror" / host
    (out / "pages").mkdir(parents=True, exist_ok=True)
    (out / "responses").mkdir(exist_ok=True)
    (out / "shots").mkdir(exist_ok=True)
    state_file = out / "state.json"
    state = json.loads(state_file.read_text("utf-8")) if state_file.exists() else {"done": [], "queue": [start]}
    done = set(state["done"])
    queue = [u for u in state["queue"] if u not in done] or ([start] if start not in done else [])
    seen = done | set(queue)
    saved_resp = set()

    def save_state():
        state_file.write_text(json.dumps({"done": sorted(done), "queue": queue}, ensure_ascii=False), "utf-8")

    with sync_playwright() as p:
        browser = launch_browser(p, args)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        def on_response(resp):
            try:
                ctype = resp.headers.get("content-type", "")
                if not TEXT_TYPES.search(ctype) or resp.url in saved_resp:
                    return
                if urlparse(resp.url).netloc.lower().removeprefix("www.") != host:
                    return
                body = resp.body()
                saved_resp.add(resp.url)
                name = h(resp.url)
                (out / "responses" / f"{name}.gz").write_bytes(gzip.compress(body))
                with (out / "responses" / "index.tsv").open("a", encoding="utf-8") as f:
                    f.write(f"{name}\t{resp.status}\t{ctype}\t{resp.url}\n")
            except PWError:
                pass

        page.on("response", on_response)

        # Если это MediaWiki — сохраняем сведения о сайте и полный список страниц через API.
        print(f"Открываю {start} …")
        page.goto(start, wait_until="domcontentloaded", timeout=60000)
        mw = out / "mediawiki"
        for api in ("/api.php", "/w/api.php"):
            api_url = urljoin(start, api)
            info = page.evaluate("""async u => { try { const r = await fetch(u + '?action=query&meta=siteinfo&siprop=general|namespaces&format=json');
                return r.ok ? await r.text() : null; } catch (e) { return null; } }""", api_url)
            if info and info.lstrip().startswith("{") and '"query"' in info:
                mw.mkdir(exist_ok=True)
                (mw / "siteinfo.json").write_text(info, "utf-8")
                print(f"Это MediaWiki ({api_url}), сохраняю список страниц…")
                pages_all = []
                for ns in (0, 6, 14):
                    cont = ""
                    while True:
                        txt = page.evaluate("async u => { const r = await fetch(u); return r.ok ? await r.text() : null; }",
                                            f"{api_url}?action=query&list=allpages&apnamespace={ns}&aplimit=500&format=json{cont}")
                        if not txt:
                            break
                        d = json.loads(txt)
                        pages_all += [dict(x, ns=ns) for x in d.get("query", {}).get("allpages", [])]
                        c = d.get("continue", {}).get("apcontinue")
                        if not c:
                            break
                        cont = "&apcontinue=" + c
                (mw / "allpages.json").write_text(json.dumps(pages_all, ensure_ascii=False, indent=1), "utf-8")
                print(f"  страниц в списке: {len(pages_all)}")
                # Исходный текст (wikitext) всех страниц пачками по 50 — это и есть основные данные.
                wt_file = mw / "wikitext.jsonl.gz"
                if not wt_file.exists():
                    ids = [x["pageid"] for x in pages_all]
                    rows = []
                    for i in range(0, len(ids), 50):
                        chunk = "|".join(map(str, ids[i:i + 50]))
                        txt = page.evaluate("async u => { const r = await fetch(u); return r.ok ? await r.text() : null; }",
                                            f"{api_url}?action=query&prop=revisions|categories|pageimages&rvprop=content"
                                            f"&rvslots=main&cllimit=max&piprop=original&format=json&pageids={chunk}")
                        if not txt:
                            print(f"  ! не удалось получить пачку {i // 50 + 1}")
                            continue
                        for pg in json.loads(txt).get("query", {}).get("pages", {}).values():
                            rev = (pg.get("revisions") or [{}])[0]
                            content = rev.get("slots", {}).get("main", {}).get("*", rev.get("*", ""))
                            rows.append({"pageid": pg.get("pageid"), "ns": pg.get("ns"), "title": pg.get("title"),
                                         "categories": [c["title"] for c in pg.get("categories", [])],
                                         "image": pg.get("original", {}).get("source"), "wikitext": content})
                        print(f"  wikitext: {min(i + 50, len(ids))}/{len(ids)}", end="\r", flush=True)
                    print()
                    wt_file.write_bytes(gzip.compress("\n".join(json.dumps(r, ensure_ascii=False) for r in rows).encode()))
                    print(f"  исходный текст {len(rows)} страниц сохранён в {wt_file.name}")
                if args.api_only:
                    # Для изучения вёрстки хватит небольшой выборки отрисованных страниц.
                    args.max_pages = min(args.max_pages, args.sample)
                base = json.loads(info)["query"]["general"].get("server", "") + \
                    json.loads(info)["query"]["general"].get("articlepath", "/wiki/$1")
                found = []
                for x in pages_all:
                    if x["ns"] == 0 or x["ns"] == 14:
                        u = norm_url(urljoin(start, base.replace("$1", x["title"].replace(" ", "_"))), host)
                        if u and u not in seen:
                            seen.add(u)
                            found.append(u)
                # Вперемешку, чтобы выборка образцов захватила страницы всех типов, а не первые по алфавиту.
                random.Random(1).shuffle(found)
                queue.extend(found)
                break

        n_done_start = len(done)
        try:
            while queue and len(done) < args.max_pages:
                url = queue.pop(0)
                try:
                    resp = page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    try:
                        page.wait_for_load_state("networkidle", timeout=5000)
                    except PWError:
                        pass
                    page.wait_for_timeout(args.wait)
                    status = resp.status if resp else 0
                    html = page.content()
                    title = page.title()
                    links = page.evaluate(LINKS_JS)
                except PWError as e:
                    print(f"  ! {url}: {str(e).splitlines()[0]}")
                    done.add(url)
                    continue
                name = h(url)
                (out / "pages" / f"{name}.html.gz").write_bytes(gzip.compress(html.encode("utf-8")))
                with (out / "pages.tsv").open("a", encoding="utf-8") as f:
                    f.write(f"{url}\t{name}\t{status}\t{title.replace(chr(9), ' ')}\n")
                n = len(done) - n_done_start
                if len(list((out / "shots").glob("*.jpg"))) < args.shots:
                    try:
                        page.screenshot(path=str(out / "shots" / f"{n:03d}_{name}.jpg"), type="jpeg", quality=50,
                                        full_page=True)
                    except PWError:
                        pass
                for link in links:
                    u = norm_url(link, host)
                    if u and u not in seen:
                        seen.add(u)
                        queue.append(u)
                done.add(url)
                print(f"  [{len(done)}, в очереди {len(queue)}] {title[:70]}")
                if n % 20 == 0:
                    save_state()
                time.sleep(args.delay)
        except KeyboardInterrupt:
            print("\nОстановлено — прогресс сохранён, можно продолжить тем же запуском.")
        finally:
            save_state()
            browser.close()
    print(f"Готово: {len(done)} страниц, осталось в очереди {len(queue)}. Результат: {out}")


if __name__ == "__main__":
    main()
