#!/usr/bin/env python3
"""Разведка структуры anteikutaern.at.ua в настоящем браузере.

Сайт подгружает категории и карточки по клику, поэтому обычный HTML-парсер их
не видит. Этот скрипт открывает каждый раздел, по очереди кликает иконки
категорий и первые несколько карточек в каждой, а после каждого клика сохраняет
HTML страницы, скриншот и все ответы сервера (AJAX/JSON/JS). По этим
примерам потом пишется точный парсер.

Запуск из корня репозитория:
    pip install playwright
    python -m playwright install chromium
    python scraper/recon.py              # все разделы
    python scraper/recon.py pets         # только питомцы
    python scraper/recon.py --headed     # смотреть, как кликает браузер
    python scraper/recon.py --browser msedge   # через установленный Edge (или chrome)
    python scraper/recon.py --browser firefox  # Firefox (сначала: python -m playwright install firefox)

Результат: папка scraper/recon/<раздел>/.
"""

import argparse
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse, urldefrag

from playwright.sync_api import sync_playwright, Error as PWError

BASE = os.environ.get("BR_BASE", "https://anteikutaern.at.ua")
OUT = Path(__file__).resolve().parent / "recon"

SECTIONS = {
    "pets": "/pety/",
    "equipment": "/dropdir/",
    "items": "/items/",
    "mobs_normal": "/mobs/mobs/",
    "mobs_bosses": "/mobs/bosses/",
    "mobs_champions": "/mobs/champions/",
    "npc": "/others/npc/",
}

TEXT_TYPES = re.compile(r"(html|json|javascript|text/plain|xml|ecmascript)", re.I)

# Находит кликабельные элементы с картинками и помечает их атрибутом data-rc.
# Курсор pointer наследуется, поэтому берём самого верхнего «кликабельного» предка.
CANDIDATES_JS = r"""
(prefix) => {
  const clickable = el => el && el !== document.body && (
    el.tagName === 'A' || el.hasAttribute('onclick') || el.getAttribute('role') === 'button' ||
    getComputedStyle(el).cursor === 'pointer');
  const visible = el => {
    const r = el.getBoundingClientRect(), st = getComputedStyle(el);
    return r.width >= 12 && r.height >= 12 && st.visibility !== 'hidden' && st.display !== 'none' && st.opacity !== '0';
  };
  const out = [], seen = new Set();
  const imgs = [...document.querySelectorAll('img, [style*="background-image"]')];
  for (const img of imgs) {
    if (!visible(img)) continue;
    let el = img, found = null;
    for (let k = 0; el && k < 8; k++, el = el.parentElement) {
      if (clickable(el)) found = el;
      else if (found) break;
    }
    if (!found || seen.has(found)) continue;
    seen.add(found);
    const id = prefix + out.length;
    found.setAttribute('data-rc', id);
    const a = found.closest('a');
    const r = found.getBoundingClientRect();
    out.push({
      id,
      tag: found.tagName.toLowerCase(),
      cls: found.className && String(found.className).slice(0, 120),
      text: (found.innerText || '').trim().replace(/\s+/g, ' ').slice(0, 100),
      img: img.currentSrc || img.src || getComputedStyle(img).backgroundImage,
      href: a ? a.href : null,
      onclick: (found.getAttribute('onclick') || '').slice(0, 200),
      x: Math.round(r.x), y: Math.round(r.y + scrollY), w: Math.round(r.width), h: Math.round(r.height),
    });
  }
  return out;
}
"""


def sig(c):
    return (c["tag"], c["img"], c["text"])


class Recon:
    def __init__(self, browser, args):
        self.browser = browser
        self.args = args
        self.saved_responses = set()

    def new_page(self, folder):
        page = self.browser.new_page(viewport={"width": 1600, "height": 1000})
        resp_dir = folder / "responses"

        def on_response(resp):
            try:
                ctype = resp.headers.get("content-type", "")
                if not TEXT_TYPES.search(ctype) or resp.url in self.saved_responses:
                    return
                body = resp.body()
                if len(body) > 3_000_000:
                    return
                self.saved_responses.add(resp.url)
                resp_dir.mkdir(parents=True, exist_ok=True)
                name = hashlib.sha1(resp.url.encode()).hexdigest()[:12]
                (resp_dir / name).write_bytes(body)
                with (resp_dir / "index.tsv").open("a", encoding="utf-8") as f:
                    f.write(f"{name}\t{resp.status}\t{resp.request.method}\t{ctype}\t{resp.url}\n")
            except PWError:
                pass

        page.on("response", on_response)
        return page

    def settle(self, page):
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except PWError:
            pass
        page.wait_for_timeout(self.args.wait)

    def snapshot(self, page, folder, name):
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{name}.html").write_text(page.content(), "utf-8")
        try:
            page.screenshot(path=str(folder / f"{name}.jpg"), type="jpeg", quality=55, full_page=True)
        except PWError as e:
            print(f"    ! screenshot {name}: {e}", file=sys.stderr)

    def open(self, page, url):
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        self.settle(page)

    def click(self, page, cid):
        try:
            page.click(f'[data-rc="{cid}"]', timeout=5000)
        except PWError:
            # элемент мог оказаться под другим — кликаем скриптом
            page.eval_on_selector(f'[data-rc="{cid}"]', "el => el.click()")
        self.settle(page)

    def candidates(self, page, prefix):
        return page.evaluate(CANDIDATES_JS, prefix)

    def run_page(self, url, folder, depth):
        print(f"  {url}")
        log = {"url": url, "categories": [], "links": []}
        page = self.new_page(folder)
        self.open(page, url)
        self.snapshot(page, folder, "00_initial")
        base_cands = self.candidates(page, "c")
        log["initial_candidates"] = base_cands
        page_url = urldefrag(page.url)[0]

        cats = []
        for c in base_cands:
            href = urldefrag(c["href"])[0] if c["href"] else None
            if href and href != page_url and urlparse(href).netloc == urlparse(url).netloc \
                    and not href.startswith("javascript:"):
                log["links"].append(c)
            else:
                cats.append(c)
        base_sigs = {sig(c) for c in base_cands}

        for ci, cat in enumerate(cats[: self.args.cats], 1):
            name = f"cat{ci:02d}"
            print(f"    категория {ci}/{len(cats)}: {cat['text'] or cat['img']}")
            entry = {"candidate": cat, "file": name, "cards": []}
            try:
                self.open(page, url)
                self.candidates(page, "c")
                self.click(page, cat["id"])
                if urldefrag(page.url)[0] != page_url:
                    entry["navigated_to"] = page.url
                self.snapshot(page, folder, name)
                after = self.candidates(page, "k")
                cards = [c for c in after if sig(c) not in base_sigs]
                entry["new_candidates"] = cards
            except PWError as e:
                entry["error"] = str(e)
                log["categories"].append(entry)
                continue

            for ki, card in enumerate(cards[: self.args.cards], 1):
                cname = f"{name}_card{ki:02d}"
                try:
                    self.open(page, url)
                    self.candidates(page, "c")
                    self.click(page, cat["id"])
                    now = self.candidates(page, "k")
                    target = next((c for c in now if sig(c) == sig(card)), None)
                    if not target:
                        entry["cards"].append({"candidate": card, "error": "не нашёлся после перезагрузки"})
                        continue
                    self.click(page, target["id"])
                    info = {"candidate": card, "file": cname}
                    if urldefrag(page.url)[0] != page_url:
                        info["navigated_to"] = page.url
                    self.snapshot(page, folder, cname)
                    entry["cards"].append(info)
                except PWError as e:
                    entry["cards"].append({"candidate": card, "error": str(e)})
            log["categories"].append(entry)

        # Если «категории» — обычные ссылки на подстраницы, разведываем несколько из них.
        if depth < 1:
            start_path = urlparse(url).path
            subs = []
            for c in log["links"]:
                h = urldefrag(c["href"])[0]
                if urlparse(h).path.startswith(start_path) and h not in subs:
                    subs.append(h)
            if not subs:
                subs = list(dict.fromkeys(urldefrag(c["href"])[0] for c in log["links"]))[: 2]
            for si, sub in enumerate(subs[: self.args.subpages], 1):
                self.run_page(sub, folder / f"sub{si:02d}", depth + 1)

        (folder / "log.json").write_text(json.dumps(log, ensure_ascii=False, indent=1), "utf-8")
        page.close()


def add_browser_args(ap):
    ap.add_argument("--headed", action="store_true", help="показать окно браузера")
    ap.add_argument("--browser", choices=["chromium", "chrome", "msedge", "firefox"], default="chromium",
                    help="chrome / msedge — установленный Google Chrome или Microsoft Edge; "
                         "firefox — Firefox от Playwright (python -m playwright install firefox)")
    ap.add_argument("--proxy", help="прокси, например http://127.0.0.1:8080 или socks5://127.0.0.1:1080")
    ap.add_argument("--no-doh", dest="doh", action="store_false",
                    help="Firefox: не включать DNS через HTTPS (Cloudflare)")


def launch_browser(p, args):
    launch = {"headless": not args.headed}
    if args.proxy:
        launch["proxy"] = {"server": args.proxy}
    if args.browser == "firefox":
        if args.doh:
            # Как в обычном Firefox с «DNS через HTTPS»: помогает, если провайдер блокирует сайт через DNS.
            launch["firefox_user_prefs"] = {
                "network.trr.mode": 2,
                "network.trr.uri": "https://mozilla.cloudflare-dns.com/dns-query",
            }
        browser = p.firefox.launch(**launch)
    else:
        if args.browser != "chromium":
            launch["channel"] = args.browser
        if os.environ.get("BR_CHROMIUM"):
            launch["executable_path"] = os.environ["BR_CHROMIUM"]
        browser = p.chromium.launch(**launch)
    return browser


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sections", nargs="*", help=f"разделы: {', '.join(SECTIONS)} (по умолчанию все)")
    ap.add_argument("--cats", type=int, default=40, help="сколько категорий кликать на странице")
    ap.add_argument("--cards", type=int, default=3, help="сколько карточек открывать в каждой категории")
    ap.add_argument("--subpages", type=int, default=3, help="сколько подстраниц-ссылок разведывать")
    ap.add_argument("--wait", type=int, default=1200, help="пауза после клика, мс")
    add_browser_args(ap)
    args = ap.parse_args()
    unknown = set(args.sections) - set(SECTIONS)
    if unknown:
        ap.error(f"неизвестные разделы: {', '.join(sorted(unknown))}")

    with sync_playwright() as p:
        browser = launch_browser(p, args)
        rc = Recon(browser, args)
        for sid in args.sections or SECTIONS:
            print(f"== {sid}")
            rc.run_page(BASE + SECTIONS[sid], OUT / sid, 0)
        browser.close()
    print(f"\nГотово. Результат в {OUT}")


if __name__ == "__main__":
    main()
