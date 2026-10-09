#!/usr/bin/env python3
"""Скачивает базу сайта anteikutaern.at.ua и все иконки к ней.

Сайт хранит все данные (экипировка, питомцы, мобы, боссы, предметы, НПС...)
в одном файле /raresImg/anteikuDB.json, а иконки — по путям вида
/raresImg/<каталог>/<img>.<каталог>.png. Скрипт открывает сайт в браузере
(так же, как recon.py), скачивает базу и иконки через сам браузер и сохраняет:

    scraper/source/anteikuDB.json        — база
    scraper/source/all_map_elements.json — объекты на картах
    scraper/source/missing_images.txt    — иконки, которые не скачались
    data/raresImg/...                    — иконки (пути как на сайте)

Запуск из корня репозитория:
    python scraper/fetch_db.py --browser firefox
    python scraper/fetch_db.py --browser firefox --maps    # ещё и картинки карт (много МБ)
    python scraper/fetch_db.py --browser firefox --no-images
"""

import argparse
import base64
import json
import os
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from recon import add_browser_args, launch_browser  # noqa: E402

BASE = os.environ.get("BR_BASE", "https://anteikutaern.at.ua")
ROOT = Path(__file__).resolve().parent.parent
SOURCE = Path(__file__).resolve().parent / "source"
IMG_ROOT = ROOT / "data"

JSON_FILES = ["anteikuDB.json", "all_map_elements.json", "anteikuDBversion.json"]
IMG_EXT = re.compile(r"\.(png|webp|jpe?g|gif|svg)$", re.I)

# Скачивает пачку файлов внутри страницы и возвращает их в base64.
FETCH_BATCH_JS = r"""
async (urls) => {
  const toB64 = blob => new Promise(res => {
    const r = new FileReader();
    r.onload = () => res(String(r.result).split(',')[1] || '');
    r.readAsDataURL(blob);
  });
  const one = async url => {
    try {
      const resp = await fetch(url, { cache: 'force-cache' });
      if (!resp.ok) return { url, status: resp.status };
      return { url, status: resp.status, b64: await toB64(await resp.blob()) };
    } catch (e) {
      return { url, status: 0, error: String(e) };
    }
  };
  const out = [];
  for (let i = 0; i < urls.length; i += 8) {
    out.push(...await Promise.all(urls.slice(i, i + 8).map(one)));
  }
  return out;
}
"""


def image_paths(db, with_maps):
    """Все пути картинок, которые удаётся вывести из базы."""
    paths = set()

    def add(p):
        p = p.strip()
        if not p or p.startswith(("http:", "https:", "data:")) and "anteikutaern" not in p:
            return
        p = re.sub(r"^https?://[^/]+", "", p)
        if not p.startswith("/"):
            p = "/" + p
        if not p.startswith("/raresImg/"):
            p = "/raresImg" + p
        if not with_maps and "/map/" in p:
            return
        paths.add(p)

    def walk(o):
        if isinstance(o, dict):
            cat, img = o.get("idCatalog"), o.get("img")
            if isinstance(cat, str) and isinstance(img, str) and img:
                add(f"{cat}/{img}" if IMG_EXT.search(img) else f"{cat}/{img}.{cat}.png")
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
        elif isinstance(o, str):
            if IMG_EXT.search(o) and "/" in o and " " not in o and len(o) < 200:
                add(o)
            for m in re.finditer(r"(?:/?raresImg/)[^\"'\s)<>]+?\.(?:png|webp|jpe?g|gif|svg)", o):
                add(m.group())

    walk(db)
    return sorted(paths)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_browser_args(ap)
    ap.add_argument("--no-images", dest="images", action="store_false", help="только база, без иконок")
    ap.add_argument("--maps", action="store_true", help="качать и картинки карт (/raresImg/map/...)")
    ap.add_argument("--force", action="store_true", help="перекачать уже скачанные иконки")
    args = ap.parse_args()

    SOURCE.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = launch_browser(p, args)
        page = browser.new_page()
        print(f"Открываю {BASE}/pety/ …")
        page.goto(BASE + "/pety/", wait_until="domcontentloaded", timeout=60000)

        for name in JSON_FILES:
            url = f"{BASE}/raresImg/{name}"
            text = page.evaluate("async u => { const r = await fetch(u); return r.ok ? await r.text() : null; }", url)
            if text is None:
                print(f"  ! не удалось скачать {name}")
                continue
            (SOURCE / name).write_text(text, "utf-8")
            print(f"  {name}: {len(text) / 1e6:.1f} МБ")

        db_file = SOURCE / "anteikuDB.json"
        if not db_file.exists():
            sys.exit("База не скачалась — пришли вывод этой команды.")
        db = json.loads(db_file.read_text("utf-8"))
        top = db.get("data", db)
        if isinstance(top, dict):
            print("Разделы базы: " + ", ".join(f"{k} ({len(v) if hasattr(v, '__len__') else '-'})"
                                               for k, v in top.items()))

        if args.images:
            maps = json.loads((SOURCE / "all_map_elements.json").read_text("utf-8")) \
                if (SOURCE / "all_map_elements.json").exists() else {}
            paths = image_paths([db, maps], args.maps)
            todo = [x for x in paths if args.force or not (IMG_ROOT / x.lstrip("/")).exists()]
            print(f"Иконок найдено: {len(paths)}, качать: {len(todo)}")
            missing = []
            for i in range(0, len(todo), 60):
                batch = todo[i:i + 60]
                for r in page.evaluate(FETCH_BATCH_JS, [BASE + x for x in batch]):
                    rel = r["url"][len(BASE):]
                    if r.get("b64"):
                        out = IMG_ROOT / rel.lstrip("/")
                        out.parent.mkdir(parents=True, exist_ok=True)
                        out.write_bytes(base64.b64decode(r["b64"]))
                    else:
                        missing.append(f"{r['status']}\t{rel}")
                print(f"  {min(i + 60, len(todo))}/{len(todo)}", end="\r", flush=True)
            print()
            (SOURCE / "missing_images.txt").write_text("\n".join(missing) + "\n", "utf-8")
            print(f"Не скачалось: {len(missing)} (список в scraper/source/missing_images.txt)")

        browser.close()
    print("Готово.")


if __name__ == "__main__":
    main()
