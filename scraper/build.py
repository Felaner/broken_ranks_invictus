#!/usr/bin/env python3
"""Собирает разделы вики из базы сайта (scraper/source/anteikuDB.json).

    python scraper/build.py

Создаёт data/<раздел>.js (+ .json) и scraper/source/needed_images.txt —
картинки, на которые ссылается вики, но которых ещё нет в data/raresImg
(их докачивает: python scraper/fetch_db.py --browser firefox --needed).
"""

import ast
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
SRC = HERE / "source"
DATA = ROOT / "data"

DB = json.loads((SRC / "anteikuDB.json").read_text("utf-8"))["data"]
MAP_NAMES = {}
_js = (SRC / "tableeqT.js").read_text("utf-8") if (SRC / "tableeqT.js").exists() else ""
for _m in re.finditer(r'\bm(\d+): "([^"/]+)"', _js):
    if re.search("[А-Яа-яЁё]", _m.group(2)):
        MAP_NAMES.setdefault("m" + _m.group(1), _m.group(2))
for _mp in DB.get("mapsMain", {}).values():
    if _mp.get("mId"):
        MAP_NAMES.setdefault(_mp["mId"], _mp["title"])

needed_images = set()


# ---------- картинки ----------

def img_rel(path):
    """'/raresImg/x/y.png' -> 'data/raresImg/x/y.png' (+ учёт в needed_images)."""
    path = re.sub(r"^https?://[^/]+", "", path.strip())
    if not path.startswith("/"):
        path = "/" + path
    if not path.startswith("/raresImg/"):
        return path
    if not (DATA / path.lstrip("/")).exists():
        needed_images.add(path)
    return "data" + path


def icon_of(o):
    cat, img = o.get("idCatalog") or "", o.get("img") or ""
    if not img or not cat:
        return ""
    if img.startswith("/raresImg/"):
        return img_rel(img)
    if cat == "lists":
        return img_rel(f"/raresImg/lists/{img}.png")
    if cat == "orb":
        return img_rel(f"/raresImg/orb/{img}_4.orb.png")
    if re.search(r"\.(png|webp|jpe?g|gif)$", img, re.I):
        return img_rel(f"/raresImg/{cat}/{img}")
    if cat == "bosses":
        return img_rel(f"/raresImg/bosses/{img}.png")
    return img_rel(f"/raresImg/{cat}/{img}.{cat}.png")


def model_of(o):
    cat, img = o.get("idCatalog") or "", o.get("imgM") or ""
    if not img or img == o.get("img") or not re.search(r"[a-z]", img):
        return ""
    if img.startswith("/raresImg/"):
        return img_rel(img)
    if re.search(r"\.(png|webp|jpe?g|gif)$", img, re.I):
        return img_rel(f"/raresImg/{cat}/{img}")
    if cat == "bosses":
        return img_rel(f"/raresImg/bosses/{img}.webp")
    return ""


# ---------- HTML ----------

ALLOWED = {"img", "br", "span", "b", "strong", "i", "em", "hr", "dl", "dt", "dd", "ul", "ol", "li", "p", "div",
           "table", "tr", "td", "th", "tbody", "small", "sup", "sub", "u", "font"}
BLOCKY = {"div", "p"}


def clean_html(html):
    """Оставляет безопасное подмножество HTML; картинки — локальные пути, связи — data-items."""
    if html is None:
        return ""
    soup = BeautifulSoup(str(html), "html.parser")
    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()
    for t in soup.find_all(["script", "style", "iframe", "video", "source"]):
        t.decompose()
    for t in list(soup.find_all(True)):
        if t.name not in ALLOWED:
            t.unwrap()
            continue
        attrs = {}
        if t.name == "img":
            if t.get("src"):
                attrs["src"] = img_rel(t["src"])
            for a in ("title", "data-items"):
                if t.get(a):
                    attrs[a] = t[a]
        else:
            if t.get("data-items"):
                attrs["data-items"] = t["data-items"]
            if t.get("data-maps"):
                attrs["data-maps"] = t["data-maps"]
            style = t.get("style", "")
            m = re.search(r"(?<![-\w])color\s*:\s*(#[0-9a-fA-F]{3,8}|[a-z]+)", style)
            if m:
                attrs["style"] = f"color:{m.group(1)}"
            if t.name == "font" and t.get("color"):
                attrs["style"] = f"color:{t['color']}"
                t.name = "span"
        if "arena-req-counter" in (t.get("class") or []):
            attrs["class"] = "cnt"
        t.attrs = attrs
    out = str(soup)
    out = re.sub(r"\s*\n\s*", " ", out).strip()
    out = re.sub(r"^(<br/?>\s*)+|(<br/?>\s*)+$", "", out)
    return out


def text_of(html):
    return re.sub(r"\s+", " ", BeautifulSoup(str(html), "html.parser").get_text(" ")).strip()


def is_html(v):
    return isinstance(v, str) and "<" in v and ">" in v


# ---------- поля ----------

LABELS = {
    "type": "Тип", "typeD": "Тип урона", "damage": "Урон", "trebLvl": "Требуемый уровень",
    "trebClass": "Требуемый класс", "trebSila": "Требуемая сила", "trebLovkost": "Требуемая ловкость",
    "trebMosh": "Требуемая мощь", "trebZnanie": "Требуемое знание",
    "sila": "Сила", "lovkost": "Ловкость", "mosh": "Мощь", "znanie": "Знание", "intellect": "Интеллект",
    "hp": "Здоровье", "mana": "Мана", "stamina": "Выносливость",
    "hpp": "Здоровье", "mmana": "Мана", "sstamina": "Выносливость",
    "resRubyashii": "Сопр. рубящим", "resDrobiashii": "Сопр. дробящим", "resKolyushii": "Сопр. колющим",
    "resOgon": "Сопр. огню", "resHolod": "Сопр. холоду", "resEnergia": "Сопр. энергии", "resMental": "Сопр. менталу",
    "cena": "Цена", "cena2": "Стоимость", "remont": "Ремонт", "remont2": "Ремонт", "zaryad": "Заряды",
    "zaryadka": "Зарядка", "emkost": "Вместимость дрифов", "drifbonus": "Усиление дрифов",
    "upgrbonus": "Усиление улучшений", "orbbonus": "Усиление орбов", "ves": "Вес", "lvl": "Уровень",
    "time": "Респаун", "arenaAsp": "Аспект арены", "powerG": "Сила (PvE)", "rang": "Ранг",
    "vampbonusM": "Мощь / Знание / Здоровье [ур. 1]", "vampbonusF": "Ловкость / Сила / Здоровье [ур. 1]",
    "orbname": "Эффект", "upgradeLvl": "Улучшение за уровень", "maxUpgrade": "Макс. улучшение",
    "nSlvl": "Уровень", "bossCt": "Кол-во", "touches": "Касания",
}
# Поля, которые выводятся отдельными HTML-блоками, а не строкой таблицы.
BLOCK_LABELS = {
    "drop": "Дроп", "dropdB": "Дроп", "bonus": "Бонус", "setName": "Комплект", "setBonus": "Бонус комплекта",
    "owner": "Где взять", "cenap": "Цена", "skills": "Навыки", "skillsB": "Навыки", "skins": "Скины",
    "team": "Команда", "teamB": "Команда", "morfs": "Образы",
    "reqB": "Требования", "petsk": "Навыки питомца", "dopbonus": "Доп. бонус", "vycup": "Выкуп",
}
SKIP = {"id", "idType", "idClass", "idCatalog", "img", "imgM", "img1", "navigation", "stats", "coordId",
        "map", "linkPage", "linkPagePL", "linkPageEN", "pageName", "mobScenar", "videoB", "mId",
        "titlePL", "titleEN", "descrPL", "descrEN", "orbnamePL", "orbnameEN", "otstup", "morf",
        "bliz", "dal", "mental", "attacks", "star", "orbs", "oskolki", "upgP", "rangp", "lvl",
        "trebLvl", "nSlvl", "p100", "p90", "p70", "zonesB", "areaMap", "mapa", "modif", "suborb",
        "biorb", "magniorb", "arhiorb", "descr3", "bossDrop", "bossCt", "reqB"}
RARITY = [("titleEpic", "Эпик"), ("titleSet", "Сет"), ("titleSin", "Синергетик"), ("titlePsy", "Психорар"),
          ("titleRar", "Рар"), ("titlePetRar", "Рар")]
ZONES = {"b": "ближняя", "d": "дальняя", "m": "ментальная"}
DIFF = (("e", "лёгк."), ("n", "норм."), ("h", "тяжел."))


def fmt(v):
    if isinstance(v, dict):
        return v
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, int) and abs(v) >= 10000:
        return f"{v:,}".replace(",", " ")
    return str(v)


def diff_value(v):
    """{'e':..,'n':..,'h':..} -> '1100' или {'e': '900', 'n': '1100', 'h': '1500'}."""
    if not isinstance(v, dict):
        return fmt(v)
    vals = [v.get(k) for k, _ in DIFF if k in v]
    vals = [x for x in vals if x not in (None, "", "-")]
    if not vals:
        return ""
    if len(set(map(str, vals))) == 1:
        return fmt(vals[0])
    # Разные значения по сложностям — интерфейс показывает выбранную.
    return {k: fmt(v.get(k, "-")) for k, _ in DIFF}


def ref_html(oid):
    """Иконка-ссылка на объект базы по его id."""
    for sec in DB.values():
        if isinstance(sec, dict) and isinstance(sec.get(oid), dict):
            o = sec[oid]
            return f'<img data-items="{oid}" src="{icon_of(o)}" title="{o.get("title", oid)}">'
    return oid


def find_title(oid):
    for sec in DB.values():
        if isinstance(sec, dict) and isinstance(sec.get(oid), dict):
            return sec[oid].get("title", oid)
    return oid


def flatten(v):
    if isinstance(v, list):
        for x in v:
            yield from flatten(x)
    elif isinstance(v, dict):
        for x in v.values():
            yield from flatten(x)
    else:
        yield v


def strip_title(html, title):
    return re.sub(r"^\s*" + re.escape(title) + r"\s*:\s*(<br/?>\s*)*", "", html, flags=re.I)


def descr_order(k):
    m = re.match(r"descr(\d*)", k)
    return int(m.group(1) or 0) if m else 0


def build_entry(o, section, category):
    title = (o.get("title") or o.get("titleItem") or o.get("id")).strip()
    fields, blocks = [], []
    level = None

    lvl = o.get("trebLvl", o.get("lvl"))
    lvl_diff = diff_value(lvl) if isinstance(lvl, dict) else None
    if isinstance(lvl, dict):
        lvl = lvl.get("n") or next((x for x in lvl.values() if isinstance(x, (int, float))), None)
    if isinstance(lvl, str) and lvl.isdigit():
        lvl = int(lvl)
    if isinstance(lvl, (int, float)) and lvl:
        level = int(lvl)
        fields.append(["Уровень" if section in ("mobs", "pets") and "lvl" in o else "Требуемый уровень",
                       lvl_diff if isinstance(lvl_diff, dict) else fmt(level)])

    rar = next((name for key, name in RARITY if o.get(key)), None)
    if rar:
        fields.append(["Редкость", rar])

    if section == "mobs":
        att = [n for k, n in (("bliz", "ближние"), ("dal", "дальние"), ("mental", "ментальные")) if o.get(k) == "+"]
        if att:
            fields.append(["Атаки", ", ".join(att)])
        if o.get("zonesB"):
            fields.append(["Зоны атаки", ", ".join(ZONES.get(z, z) for z in o["zonesB"])])
        for k, n in (("p100", "100%"), ("p90", "90%"), ("p70", "70%")):
            if o.get(k):
                fields.append([f"Шанс дропа {n} — уровни", diff_value(o[k])])
        if o.get("idClass", "").startswith("bosses"):
            fields.append(["Группа боссов", BOSS_GROUPS.get(o["idClass"], o["idClass"])])

    up = [n for k, n in (("star", "звёзды"), ("orbs", "орбы"), ("oskolki", "осколки")) if o.get(k) == "+"]
    if up and section != "items":
        fields.append(["Улучшения", ", ".join(up)])

    for k in ("upgP", "rangp"):
        if isinstance(o.get(k), str) and ":" in o[k]:
            a, b = o[k].split(":", 1)
            fields.append([a.strip(), b.strip()])

    recipes, makers = [], []
    for k, v in o.items():
        if k.startswith("forCrt") and isinstance(v, list):
            for r in v:
                if not isinstance(r, dict):
                    continue
                price = clean_html(r.get("price", ""))
                kind = r.get("type") or "Создание"
                recipes.append(f"<b>{kind}:</b> {price}" if price else f"<b>{kind}</b>")
                if r.get("who"):
                    makers.append(clean_html(r["who"]))
    if recipes:
        blocks.append({"title": "Рецепт", "html": "<br>".join(recipes)})
    if makers:
        blocks.append({"title": "Где создать", "html": " ".join(dict.fromkeys(makers))})

    descr_parts = []
    for k, v in o.items():
        if k in SKIP or k.startswith(("title", "otstup", "forCrt")) or v in (None, "", [], {}):
            continue
        if v == "+" and k in BLOCK_LABELS:
            continue
        if k.startswith("descr"):
            descr_parts.append((descr_order(k), v))
            continue
        if k in BLOCK_LABELS or is_html(v) or (isinstance(v, list) and any(is_html(x) for x in flatten(v))):
            html = " ".join(clean_html(x) for x in flatten(v) if isinstance(x, str)) \
                if isinstance(v, list) else clean_html(v)
            btitle = BLOCK_LABELS.get(k, LABELS.get(k, k))
            html = strip_title(html, btitle)
            if text_of(html) or "<img" in html:
                blocks.append({"title": btitle, "html": html})
            continue
        if isinstance(v, dict):
            v = diff_value(v)
        elif isinstance(v, list):
            v = ", ".join(map(fmt, v))
        if v in ("", "+"):
            continue
        if k == "trebClass":
            v = CLASSES.get(v, v)
        if k in ("sila", "lovkost", "mosh", "znanie", "hp", "mana", "stamina", "intellect") \
                and section in ("equipment", "pets") and str(v) == "0":
            continue
        if k.startswith("res") and str(v) == "0":
            continue
        if k in ("drifbonus", "upgrbonus", "orbbonus") and str(v) == "0":
            continue
        fields.append([LABELS.get(k, k), fmt(v)])

    if isinstance(o.get("reqB"), dict) and any(o["reqB"].values()):
        parts = []
        for k, n in (("all", "все сложности"),) + DIFF:
            vals = o["reqB"].get(k) or []
            if not vals:
                continue
            out, count = [], None
            for v in vals:
                if isinstance(v, (int, float)):
                    count = fmt(v)
                    continue
                icon = clean_html(v) if is_html(v) else ref_html(str(v))
                out.append(f"{icon} ×{count}" if count else icon)
                count = None
            parts.append(f"<b>{n}:</b> " + " ".join(out))
        blocks.append({"title": "Требования для входа", "html": "<br>".join(parts)})

    modif = o.get("modif")
    if isinstance(modif, str) and modif.startswith("{"):
        try:
            modif = ast.literal_eval(modif)
        except (ValueError, SyntaxError):
            modif = None
    if isinstance(modif, dict) and modif:
        items = []
        for _, pair in modif.items():
            if isinstance(pair, list) and len(pair) == 2:
                mod = DB.get("modsMain", {}).get(pair[0], {})
                items.append(f"{mod.get('title', pair[0])} +{fmt(pair[1])}")
        if items:
            blocks.append({"title": "Модификаторы", "html": "<br>".join(items)})

    for key, name in (("suborb", "Суб"), ("biorb", "Би"), ("magniorb", "Магни"), ("arhiorb", "Архи")):
        if o.get(key):
            fields.append([f"{name}-орб", " / ".join(map(fmt, o[key]))])

    if isinstance(o.get("mapa"), dict) and o["mapa"].get("ru"):
        fields.append(["Расположение", o["mapa"]["ru"]])
    if o.get("areaMap"):
        flat = []
        for m in o["areaMap"]:
            flat.extend(m if isinstance(m, list) else [m])
        ids = list(dict.fromkeys(m for m in flat if isinstance(m, str)))
        links = [f'<span data-maps="{m}">{MAP_NAMES.get(m, m)}</span>' for m in ids]
        blocks.append({"title": "Путь по картам" if section == "mobs" else "Где найти",
                       "html": " → ".join(links) if section == "mobs" else ", ".join(links)})

    descr = " <br>".join(clean_html(v) for _, v in sorted(descr_parts, key=lambda x: x[0]) if clean_html(v))
    if descr:
        blocks.insert(0, {"title": "Описание", "html": descr})

    model = model_of(o)
    return {
        "id": o["id"],
        "category": category,
        "name": title,
        "nameEN": o.get("titleEN", ""),
        "namePL": o.get("titlePL", ""),
        "icon": icon_of(o),
        "image": model,
        "level": level,
        "fields": fields,
        "blocks": blocks,
        "sourceUrl": SECTION_URL[section],
    }


# ---------- разделы ----------

SECTION_URL = {
    "equipment": "https://anteikutaern.at.ua/dropdir/",
    "pets": "https://anteikutaern.at.ua/pety/",
    "mobs": "https://anteikutaern.at.ua/mobs/mobs/",
    "items": "https://anteikutaern.at.ua/items/",
    "npc": "https://anteikutaern.at.ua/others/npc/",
    "skills": "https://anteikutaern.at.ua/",
}
CLASSES = {"ryc": "Рыцарь", "dru": "Друид", "om": "Огненный маг", "vd": "Вуду", "monk": "Шид",
           "var": "Варвар", "luk": "Лучник"}
BOSS_GROUPS = {"bossesNep": "Непокой", "bossesStr": "Страх", "bossesTrv": "Тревога", "bossesUzhs": "Ужас"}

EQUIP = [  # (раздел базы, категория, название)
    ("helmetsMain", "helmets", "Шлемы"), ("amuletsMain", "amulets", "Амулеты"),
    ("armorsMain", "armors", "Броня"), ("capesMain", "capes", "Плащи"),
    ("bracersMain", "bracers", "Наручи"), ("glovesMain", "gloves", "Перчатки"),
    ("ringsMain", "rings", "Кольца"), ("beltsMain", "belts", "Пояса"),
    ("pantsMain", "pants", "Штаны"), ("bootsMain", "boots", "Сапоги"),
]
WEAPON_CATS = [
    ("weaponsAxePSY", "axe", "Топоры"), ("weaponsAxe_thPSY", "axe_th", "Двуручные топоры"),
    ("weaponsSwordPSY", "sword", "Мечи"), ("weaponsSword_thPSY", "sword_th", "Двуручные мечи"),
    ("weaponsHammerPSY", "hammer", "Молоты"), ("weaponsHammer_thPSY", "hammer_th", "Двуручные молоты"),
    ("weaponsKnucklesPSY", "knuckles", "Кастеты"), ("weaponsStickPSY", "stick", "Палочки"),
    ("weaponsBowPSY", "bow", "Луки"), ("weaponsShieldPSY", "shield", "Щиты"),
    ("weaponsEpic", "epic", "Эпическое оружие"),
]
PET_CATS = [("obichpets", "Обычные"), ("receptpets", "Рецептурные"), ("guildpets", "Гильдейские"),
            ("onetimepets", "Одноразовые"), ("specialpets", "Особые"), ("petB", "Доспехи питомца"),
            ("petO", "Горжеты"), ("petP", "Повязки"), ("petskin", "Скины")]
ITEM_CATS = [("isyrie", "Сырьё"), ("isvragov", "С врагов"), ("iklychi", "Ключи"), ("idobicha", "Добыча"),
             ("iresursi", "Ресурсы"), ("iflyagi", "Фляги и зелья"), ("iobmen", "Обмен"),
             ("iszadanii", "С заданий"), ("iraznoe", "Разное")]
ORB_CATS = [("orbattack", "Орбы атаки"), ("orbdef", "Орбы защиты"), ("orbunivers", "Универсальные орбы")]


def equipment():
    cats, entries = [], []
    for sec, cid, name in EQUIP:
        cats.append({"id": cid, "name": name})
        for o in DB[sec].values():
            if o.get("idClass", "").endswith("Skins"):
                continue
            entries.append(build_entry(o, "equipment", cid))
    wcls = {c: cid for c, cid, _ in WEAPON_CATS}
    for _, cid, name in WEAPON_CATS:
        cats.append({"id": cid, "name": name})
    cats.append({"id": "sets", "name": "Оружие комплектов"})
    for o in DB["weaponsMain"].values():
        cls = o.get("idClass", "")
        if cls.endswith("Skins"):
            continue
        entries.append(build_entry(o, "equipment", wcls.get(cls, "sets")))
    cats.append({"id": "kits", "name": "Комплекты"})
    for o in DB["othersMain"].values():
        if o.get("idClass") == "setlists" and o.get("descr"):
            e = build_entry(o, "equipment", "kits")
            e["name"] = re.sub(r"^Сет\s+", "", e["name"])
            for b in e["blocks"]:
                b["title"] = {"Описание": "Части комплекта", "Модификаторы": "Бонус комплекта",
                              "Дроп": "Где добыть"}.get(b["title"], b["title"])
                if b["title"] == "Части комплекта":
                    ids = list(dict.fromkeys(re.findall(r'data-items="([^"]+)"', b["html"])))
                    b["html"] = "<br>".join(f'{ref_html(i)} {find_title(i)}' for i in ids)
            e["fields"] = [f for f in e["fields"] if f[0] != "Тип"]
            entries.append(e)
    cats.append({"id": "skins", "name": "Образы (скины)"})
    for sec in [s for s, _, _ in EQUIP] + ["weaponsMain"]:
        for o in DB[sec].values():
            if o.get("idClass", "").endswith("Skins"):
                entries.append(build_entry(o, "equipment", "skins"))
    return cats, entries


def by_class(sec, catmap, section):
    cats = [{"id": c, "name": n} for c, n in catmap]
    known = {c for c, _ in catmap}
    entries = []
    for o in DB[sec].values():
        if not o.get("id"):  # служебные записи (например, orbInfo)
            continue
        cls = o.get("idClass") or "_"
        if cls not in known:
            cats.append({"id": cls, "name": cls})
            known.add(cls)
        entries.append(build_entry(o, section, cls))
    return cats, entries


def mobs():
    cats = [{"id": "normal", "name": "Обычные"}, {"id": "elite", "name": "Элита"},
            {"id": "bosses", "name": "Боссы"}, {"id": "champions", "name": "Чемпионы"}]
    entries = [build_entry(o, "mobs", "elite" if o.get("idClass") == "elita" else "normal")
               for o in DB["enemiesMain"].values()]
    entries += [build_entry(o, "mobs", "bosses") for o in DB["bossMain"].values()]
    entries += [build_entry(o, "mobs", "champions") for o in DB["champsMain"].values()]
    return cats, entries


def items():
    cats, entries = by_class("itemsMain", ITEM_CATS, "items")
    oc, oe = by_class("orbsMain", ORB_CATS, "items")
    oe = [e for e in oe if e["category"] != "_"]
    return cats + [c for c in oc if c["id"] != "_"], entries + oe


SECTIONS_OUT = {}

# Как называется обратная связь: (раздел-источник или "*", заголовок блока) -> заголовок у цели.
REVERSE = {
    ("mobs", "Дроп"): "Падает с",
    ("*", "Дроп"): "Дропает",
    ("*", "Где добыть"): "Дропает (комплекты)",
    ("*", "Навыки"): "Есть у",
    ("*", "Команда"): "В команде у",
    ("*", "Требования для входа"): "Нужен для входа к",
    ("*", "Где взять"): "Продаёт / выдаёт",
    ("*", "Рецепт"): "Ингредиент для",
    ("*", "Где создать"): "Создаёт",
    ("*", "Части комплекта"): "Входит в комплект",
    ("*", "Скины"): "Скин для",
    ("*", "Цена"): "Оплата за",
    ("*", "Образы"): "Образ для",
}


def add_backrefs():
    known = {e["id"]: e for _, ents in SECTIONS_OUT.values() for e in ents}
    back = {}
    for sid, (_, entries) in SECTIONS_OUT.items():
        for e in entries:
            for b in e["blocks"]:
                title = REVERSE.get((sid, b["title"])) or REVERSE.get(("*", b["title"])) or "Упоминается в"
                for tid in dict.fromkeys(re.findall(r'data-items="([^"]+)"', b["html"])):
                    if tid != e["id"] and tid in known:
                        back.setdefault(tid, {}).setdefault(title, [])
                        if e["id"] not in back[tid][title]:
                            back[tid][title].append(e["id"])
    for tid, groups in back.items():
        # Не повторяем то, что уже есть в собственных блоках записи.
        own = set(re.findall(r'data-items="([^"]+)"', " ".join(b["html"] for b in known[tid]["blocks"])))
        refs = [{"title": t, "ids": [i for i in ids if i not in own]} for t, ids in groups.items()]
        known[tid]["backrefs"] = [r for r in refs if r["ids"]]
    print(f"Обратных связей: {sum(len(i) for g in back.values() for i in g.values())}")


def build_maps():
    """data/maps.js: карты с картинками, порталами и точками объектов."""
    images = {}
    m = re.search(r"const MAPS = \{(.*?)\};", _js, re.S)
    if m:
        for k, v in re.findall(r'(m\d+): "([^"]+)"', m.group(1)):
            images[k] = v
    elements = {}
    me = SRC / "all_map_elements.json"
    if me.exists():
        elements = json.loads(me.read_text("utf-8")).get("data", {})
    known = {e["id"] for _, ents in SECTIONS_OUT.values() for e in ents}

    maps = {}

    def get(mid):
        if mid not in maps:
            maps[mid] = {"id": mid, "name": MAP_NAMES.get(mid, mid),
                         "image": img_rel(images[mid]) if mid in images else "",
                         "portals": [], "points": []}
        return maps[mid]

    def add_point(mid, oid, c):
        if oid not in known or not isinstance(c, dict) or "x" not in c:
            return
        pts = get(mid)["points"]
        if not any(p["id"] == oid and abs(p["x"] - c["x"]) < 0.5 and abs(p["y"] - c["y"]) < 0.5 for p in pts):
            pts.append({"id": oid, "x": c["x"], "y": c["y"]})

    for mid, el in elements.items():
        mp = get(mid)
        for p in el.get("portals", []):
            c = p.get("coordId") or {}
            if "x" in c and p.get("targetMap"):
                mp["portals"].append({"to": p["targetMap"], "x": c["x"], "y": c["y"]})
        for kind in ("npc", "items", "enemies", "others"):
            for it in el.get(kind, []):
                add_point(mid, it.get("id"), it.get("coordId"))
    for mid in images:
        get(mid)
    for o in (x for sec in DB.values() if isinstance(sec, dict) for x in sec.values() if isinstance(x, dict)):
        areas, coords = o.get("areaMap"), o.get("coordId")
        if isinstance(areas, list) and isinstance(coords, list):
            for a, c in zip(areas, coords):
                for mid in (a if isinstance(a, list) else [a]):
                    if isinstance(mid, str):
                        add_point(mid, o.get("id"), c)
    for mp in maps.values():
        for p in mp["portals"]:
            p["name"] = MAP_NAMES.get(p["to"], p["to"])
    for mp in maps.values():
        # У части карт на сайте вместо имени заглушка — подписываем номером и уводим в конец.
        if mp["name"] in ("Название", mp["id"]):
            mp["name"] = f"Безымянная локация №{mp['id'][1:]}"
            mp["unnamed"] = True
    out = sorted(maps.values(), key=lambda x: (bool(x.get("unnamed")), int(re.sub(r"\D", "", x["id"]) or 0)))
    payload = json.dumps(out, ensure_ascii=False, separators=(",", ":"))
    (DATA / "maps.js").write_text(f"window.BR_MAPS = {payload};\n", "utf-8")
    print(f"maps: {len(out)} карт, точек: {sum(len(x['points']) for x in out)}, "
          f"порталов: {sum(len(x['portals']) for x in out)}")


# ---------- wikibr.pl ----------

WB_KIND_SECTIONS = {"item": ("items", "equipment", "pets"), "mob": ("mobs",), "champion": ("mobs",),
                    "pet": ("pets",)}
WB_CATS = [("guides", "Гайды", ("guide",)), ("classes", "Классы", ("class",)),
           ("locations", "Локации", ("location",)), ("instances", "Инстансы", ("instance",)),
           ("other", "Прочее", ("item", "mob", "pet", "champion"))]
needed_wikibr = set()


def slug(t):
    import unicodedata
    t = unicodedata.normalize("NFKD", t.replace("ł", "l").replace("Ł", "L"))
    return re.sub(r"[^a-z0-9]+", "_", t.encode("ascii", "ignore").decode().lower()).strip("_") or "x"


def wb_norm(t):
    return re.sub(r"\s+", " ", (t or "").lower()).strip()


# Перевод польских текстов: словарь фрагментов (scraper/source/translate_pl_ru.json)
# плюс названия объектов из базы (titlePL -> title). Непереведённое копится в translate_todo.json.
TR_FILE = SRC / "translate_pl_ru.json"
TR = json.loads(TR_FILE.read_text("utf-8")) if TR_FILE.exists() else {}
PL2RU = {}
for _sec in DB.values():
    if isinstance(_sec, dict):
        for _o in _sec.values():
            if isinstance(_o, dict) and _o.get("titlePL") and _o.get("title"):
                PL2RU.setdefault(_o["titlePL"].strip().lower(), _o["title"].strip())
untranslated = Counter()
LATIN = re.compile(r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]")


# Шаблоны с числами: «300 platyny», «30 minut», «48H», «20-40 lvl», «10 000 złota».
TR_PATTERNS = [
    (re.compile(r"^([\d\s.,]+)\s*złot(a|ych|o|e)?$", re.I), r"\1 золота"),
    (re.compile(r"^([\d\s.,]+)\s*platyn(y|a)?$", re.I), r"\1 платины"),
    (re.compile(r"^([\d\s.,]+)\s*minut(y|a)?$", re.I), r"\1 мин"),
    (re.compile(r"^([\d\s.,]+)\s*sekund(y|a)?$", re.I), r"\1 сек"),
    (re.compile(r"^([\d\s.,]+)\s*godzin(y|a)?$", re.I), r"\1 ч"),
    (re.compile(r"^([\d\s.,]+)\s*dni$", re.I), r"\1 дн."),
    (re.compile(r"^(\d+)\s*H$"), r"\1 ч"),
    (re.compile(r"^([\d\s]+(?:[-–]\s*[\d\s]+)?)\s*lvl$", re.I), r"\1 ур."),
    (re.compile(r"^([\d\s]+)\s*szt\.?$", re.I), r"\1 шт."),
    (re.compile(r"^(\d+)\s*x$", re.I), r"\1 ×"),
    (re.compile(r"^x$", re.I), "×"),
    (re.compile(r"^(\d+)\s*vs\s*(\d+)$", re.I), r"\1 на \2"),
    (re.compile(r"^([IVX]+)$"), r"\1"),
    (re.compile(r"^(\d+)\s*PA$"), r"\1 ОД"),
    (re.compile(r"^Subdrif (\w+)$"), r"Субдриф \1"),
    (re.compile(r"^Bidrif (\w+)$"), r"Бидриф \1"),
    (re.compile(r"^Magnidrif (\w+)$"), r"Магнидриф \1"),
    (re.compile(r"^Arcydrif (\w+)$"), r"Архидриф \1"),
    (re.compile(r"^lvl \* (-?[\d.]+)$"), r"ур. × \1"),
    (re.compile(r"^Obrażenia: \((\d+)\s*\+\s*lvl\)$"), r"Урон: (\1 + ур.)"),
    (re.compile(r"^\+(\d+)% \+ Wzór$"), r"+\1% + формула"),
    (re.compile(r"^\+(\d+) i \+([\d.,]+)%$"), r"+\1 и +\2%"),
    (re.compile(r"^(\d+) poziom postaci([.,])$"), r"\1 уровень персонажа\2"),
    (re.compile(r"^Ilość ładunków (\d+)\.$"), r"Количество зарядов: \1."),
    (re.compile(r"^(\d+) Imperiałów$"), r"\1 империалов"),
    (re.compile(r"^Suborb (\S+)$"), r"Суборб \1"),
    (re.compile(r"^Biorb (\S+)$"), r"Биорб \1"),
    (re.compile(r"^Magniorb (\S+)$"), r"Магниорб \1"),
    (re.compile(r"^Arcyorb (\S+)$"), r"Архиорб \1"),
    (re.compile(r"^Ranga ([IVX]+)(?: - ([IVX]+))?$"), lambda m: "Ранг " + m.group(1) + ("–" + m.group(2) if m.group(2) else "")),
    (re.compile(r"^([\d\s]+) doświadczenia([.,]?)$"), r"\1 опыта\2"),
    (re.compile(r"^([\d\s]+) złota([.,]?)$"), r"\1 золота\2"),
    (re.compile(r"^([\d\s]+) złota i ([\d\s]+) platyny([.,]?)$"), r"\1 золота и \2 платины\3"),
    (re.compile(r"^Wartość: ([\d\s]+) złota i ([\d\s]+) platyny$"), r"Цена: \1 золота и \2 платины"),
    (re.compile(r"^Zdobyty przez: (.+)$"), r"Получен игроком: \1"),
    (re.compile(r"^Uwaga statystyki przedmiotu \+(\d+)$"), r"Внимание: характеристики предмета +\1"),
    (re.compile(r"^(\d+) (Kryształów|Żelaza|Desek|Kamienia) (?:na )?godzinę\.$"),
     lambda m: m.group(1) + " " + {"Kryształów": "кристаллов", "Żelaza": "железа", "Desek": "досок", "Kamienia": "камня"}[m.group(2)] + " в час."),
    (re.compile(r"^Zwiększa maksymalną liczbę członków gildii do (\d+)$"), r"Увеличивает максимальное число членов гильдии до \1"),
    (re.compile(r"^Klatka (\d) - (\d+) miejsc[ae]?$"), r"Клетка \1 — \2 мест"),
    (re.compile(r"^Dostępne od Rangi ([IVX]+)$"), r"Доступно с ранга \1"),
    (re.compile(r"^(\d+) punktów$"), r"\1 очков"),
    (re.compile(r"^(\d+)% frakcji$"), r"\1% фракции"),
]


def tr_names(text):
    """Перевод перечня названий («Pies, Psiok;») по словарю и базе, непереведённое остаётся."""
    parts = re.split(r"(,\s*|;\s*|\s+i\s+)", text)
    out = []
    for part in parts:
        if re.fullmatch(r",\s*|;\s*", part or ""):
            out.append(part)
        elif re.fullmatch(r"\s+i\s+", part or ""):
            out.append(" и ")
        elif part:
            m = re.match(r"^(.*?)(\s*\(.*\))?$", part)
            name = m.group(1)
            t = tr_core(name) if LATIN.search(name) else name
            out.append((t if t is not None else name) + (m.group(2) or ""))
    return "".join(out)


TIME_UNITS = {"h": "ч", "min": "мин", "sec": "сек", "m": "мин"}


def tr_time(m):
    return re.sub(r"(\d+)\s*(h|min|sec|m)\b", lambda x: x.group(1) + " " + TIME_UNITS[x.group(2)],
                  m.group(0)).replace(" - ", " – ")


XP_WHO = {"gracza": "игроку", "zwierzaka": "питомцу", "drifów": "дрифам"}
TR_FUNCS = [
    (re.compile(r"^(?:\d+\s*(?:h|min|sec|m)\s*)+(?:-\s*(?:\d+\s*(?:h|min|sec|m)\s*)+)?$"), tr_time),
    (re.compile(r"^(ok\. )?([\d\s]+) punktów doświadczenia dla (gracza|zwierzaka|drifów)([.,;]?)$"),
     lambda m: ("ок. " if m.group(1) else "") + m.group(2).strip() + " опыта " + XP_WHO[m.group(3)] + m.group(4)),
    (re.compile(r"^(ok\. )?([\d\s]+) złota([.,;]?)$"), lambda m: ("ок. " if m.group(1) else "") + m.group(2).strip() + " золота" + m.group(3)),
    (re.compile(r"^Upoluj: (\d+) x (.+)$"), lambda m: f"Убей: {m.group(1)} × " + tr_names(m.group(2))),
    (re.compile(r"^Odnajdź: (.+)$"), lambda m: "Найди: " + tr_names(m.group(1))),
    (re.compile(r"^Znajdź i zabij drużynę: (.+)$"), lambda m: "Найди и убей отряд: " + tr_names(m.group(1))),
    (re.compile(r"^Znajdź i przynieś: (\d+) x(.*)$"), lambda m: f"Найди и принеси: {m.group(1)} ×" + tr_names(m.group(2))),
    (re.compile(r"^Pokonaj (.+?)\.?$"), lambda m: "Победи: " + tr_names(m.group(1)) + "."),
    (re.compile(r"^.+ Kategoria: .*: Описание$"), lambda m: "Описание"),
    (re.compile(r"^.+: Описание$"), lambda m: "Описание"),
    (re.compile(r"^100 \+ (\d+)% max zasobów$"), lambda m: f"100 + {m.group(1)}% макс. ресурсов"),
    (re.compile(r"^([+\-][\d.,]+%?) i ([+\-][\d.,]+%?)$"), lambda m: f"{m.group(1)} и {m.group(2)}"),
    (re.compile(r"^\+([\d.,]+)% \+ Wzór$"), lambda m: f"+{m.group(1)}% + формула"),
    (re.compile(r"^(\d+)( i więcej)? dn(?:i|zień) serii - \+(\d+)% Bonusu[;,.]?$"),
     lambda m: f"{m.group(1)}{' и более' if m.group(2) else ''} дн. серии — +{m.group(3)}% бонуса"),
    (re.compile(r"^Wytworzenie podczas Eventu (.+?) w (\d{4}) r\.$"),
     lambda m: f"Изготовление во время ивента «{tr_names(m.group(1))}» в {m.group(2)} г."),
    (re.compile(r"^W (\d{4}) r\. by(?:ł|ły) nagrodą za wykonanie Questu Eventowego$"),
     lambda m: f"В {m.group(1)} г. — награда за выполнение ивентового квеста"),
    (re.compile(r"^Do kupienia w trakcie eventu (zimowego|Black Friday|dziady) w (\d{4}) r\.$"),
     lambda m: "Можно было купить во время " + {"zimowego": "зимнего ивента", "Black Friday": "ивента «Чёрная пятница»",
                                                  "dziady": "ивента «Дзяды»"}[m.group(1)] + f" в {m.group(2)} г."),
    (re.compile(r"^w (\d{4}) r\.$"), lambda m: f"в {m.group(1)} г."),
    (re.compile(r"^Otrzymał go gracz o nicku: (.+)$"), lambda m: f"Его получил игрок с ником {m.group(1)}"),
    (re.compile(r"^([\d\s]+) platyny - (kompletny )?zestaw(.*)$"),
     lambda m: f"{m.group(1).strip()} платины — {'полный ' if m.group(2) else ''}комплект" + tr_names(m.group(3))),
    (re.compile(r"^(\d+) - (\d+) poziom postaci:$"), lambda m: f"{m.group(1)}–{m.group(2)} уровень персонажа:"),
]


def tr_core(core):
    """Перевод фрагмента без крайних пробелов или None, если перевода нет."""
    if not LATIN.search(core):
        return core
    if core in TR:
        return TR[core]
    for rx, rep in TR_PATTERNS:
        if rx.match(core):
            return rx.sub(rep, core)
    for rx, fn in TR_FUNCS:
        m = rx.match(core)
        if m:
            return fn(m)
    m = re.match(r"^(.*?)([\s,.:;!?)]*)$", core)
    if m.group(1).lower() in PL2RU:
        return PL2RU[m.group(1).lower()] + m.group(2)
    if m.group(1) in TR:
        return TR[m.group(1)] + m.group(2)
    # «Метка: значение» и «: значение»
    lm = re.match(r"^([^:]{0,40}?)\s*:\s*(.*)$", core)
    if lm:
        label = tr_core(lm.group(1)) if lm.group(1) else ""
        value = tr_core(lm.group(2)) if lm.group(2) else ""
        if label is not None and value is not None:
            return (label + ": " + value).strip() if lm.group(1) else (": " + value).rstrip()
    # «Метка +число» (характеристики предметов: «Pancerz kłute +37»)
    pm = re.match(r"^(.+?)\s*([+\-]\s*[\d.,]+%?)$", core)
    if pm and pm.group(1) in TR:
        return TR[pm.group(1)] + " " + pm.group(2)
    return None


def tr_text(s):
    core = re.sub(r"\s+", " ", s).strip()
    if not core or not LATIN.search(core):
        return s
    out = tr_core(core)
    if out is None:
        untranslated[core] += 1
        out = core
    lead = " " if s[:1].isspace() else ""
    trail = " " if s[-1:].isspace() else ""
    return lead + out + trail


def tr_html(html):
    soup = BeautifulSoup(html, "html.parser")
    for node in list(soup.find_all(string=True)):
        if isinstance(node, Comment):
            continue
        new = tr_text(str(node))
        if new != str(node):
            node.replace_with(new)
    for t in soup.find_all(title=True):
        t["title"] = tr_text(t["title"]).strip()
    return str(soup)


def add_wikibr():
    """Встраивает данные второй вики (scraper/source/wikibr.json) в наши записи и создаёт раздел «Статьи»."""
    f = SRC / "wikibr.json"
    if not f.exists():
        return
    pages = json.loads(f.read_text("utf-8"))["pages"]
    redirects = {t: p["target"] for t, p in pages.items() if p["kind"] == "redirect"}
    by_pl = {}
    for sid, (_, entries) in SECTIONS_OUT.items():
        for e in entries:
            if e.get("namePL"):
                by_pl.setdefault(wb_norm(e["namePL"]), []).append((sid, e))

    title_to_id, matched, new_entries = {}, [], []
    for title, p in pages.items():
        if p["kind"] == "redirect":
            continue
        cands = by_pl.get(wb_norm(title), [])
        if p["kind"] in WB_KIND_SECTIONS:
            pref = [e for sid, e in cands if sid in WB_KIND_SECTIONS[p["kind"]]]
            cands = pref or [e for _, e in cands]
        else:
            cands = []
        if cands:
            matched.append((p, cands))
            title_to_id[title] = cands[0]["id"]
        else:
            cat = next(c for c, _, kinds in WB_CATS if p["kind"] in kinds)
            eid = "wb_" + slug(title)
            img = p.get("image")
            e = {"id": eid, "category": cat, "name": tr_text(title).strip(), "nameEN": "", "namePL": title,
                 "icon": wb_img(img) if img else "", "image": "", "level": None,
                 "fields": [], "blocks": [], "sourceUrl": ""}
            new_entries.append((p, e))
            title_to_id[title] = eid
    for src, dst in redirects.items():
        if dst in title_to_id:
            title_to_id[src] = title_to_id[dst]

    def convert(html):
        def link(m):
            tid = title_to_id.get(m.group(1)) or title_to_id.get(redirects.get(m.group(1), ""))
            return f'data-items="{tid}"' if tid else ""
        html = re.sub(r'data-wikibr="([^"]+)"', link, html)
        html = re.sub(r'data-wikibr-img="([^"]+)"', lambda m: f'src="{wb_img(m.group(1))}"', html)
        return tr_html(html)

    def merge(e, p):
        """Блоки с тем же заголовком дополняются, новые — добавляются; простые поля — в таблицу."""
        have_fields = {k for k, _ in e["fields"]}
        for k, v in p.get("fields", []):
            label = tr_text(k).strip()
            if "<" in v:
                add_block(e, label, convert(v))
            elif label not in have_fields:
                e["fields"].append([label, tr_text(v).strip()])
                have_fields.add(label)
        for b in p.get("blocks", []):
            add_block(e, tr_text(b["title"]).strip(), convert(b["html"]))

    def add_block(e, title, html):
        for b in e["blocks"]:
            if b["title"] == title:
                b["html"] += "<hr>" + html
                return
        e["blocks"].append({"title": title, "html": html})

    for p, cands in matched:
        for e in cands:
            merge(e, p)
    for p, e in new_entries:
        merge(e, p)
    cats = [{"id": c, "name": n} for c, n, _ in WB_CATS]
    write("guides", cats, [e for _, e in new_entries])
    todo = [{"pl": k, "count": n} for k, n in untranslated.most_common()]
    (SRC / "translate_todo.json").write_text(json.dumps(todo, ensure_ascii=False, indent=0), "utf-8")
    print(f"Вторая вики: дополнено записей {sum(len(c) for _, c in matched)}, новых статей {len(new_entries)}; "
          f"непереведённых фрагментов: {len(untranslated)} (scraper/source/translate_todo.json)")


def wb_img(path):
    """'/images/5/56/X.png' -> 'data/wikibr/images/5/56/X.png' (+ в список на скачивание)."""
    from urllib.parse import unquote
    if not (DATA / "wikibr" / unquote(path).lstrip("/")).exists():
        needed_wikibr.add(path)
    return "data/wikibr" + path


def write(sid, cats, entries):
    SECTIONS_OUT[sid] = (cats, entries)


def write_out(sid, cats, entries):
    ids = Counter(e["id"] for e in entries)
    dup = [i for i, n in ids.items() if n > 1]
    if dup:
        print(f"  ! повторяющиеся id в {sid}: {dup[:5]}")
    cats = [c for c in cats if any(e["category"] == c["id"] for e in entries)]
    data = {"updated": date.today().isoformat(), "categories": cats, "entries": entries}
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    (DATA / f"{sid}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), "utf-8")
    (DATA / f"{sid}.js").write_text(f"(window.BR_DATA = window.BR_DATA || {{}})[{json.dumps(sid)}] = {payload};\n",
                                    "utf-8")
    print(f"{sid}: {len(entries)} записей, категорий: {len(cats)}")


def main():
    DATA.mkdir(exist_ok=True)
    if (SRC.parent / "mirror" / "wikibr.pl" / "pages.tsv").exists():
        import wikibr
        wikibr.main()
    write("equipment", *equipment())
    write("pets", *by_class("petsMain", PET_CATS, "pets"))
    write("mobs", *mobs())
    write("items", *items())
    write("npc", [], [build_entry(o, "npc", "_") for o in DB["npcMain"].values()])
    write("skills", [], [build_entry(o, "skills", "_") for o in DB["skillsMain"].values()])
    add_wikibr()
    add_backrefs()
    for sid, (cats, entries) in SECTIONS_OUT.items():
        write_out(sid, cats, entries)
    build_maps()
    (SRC / "needed_images.txt").write_text("\n".join(sorted(needed_images)) + "\n", "utf-8")
    print(f"Недостающих картинок: {len(needed_images)} (scraper/source/needed_images.txt)")
    (SRC / "needed_wikibr.txt").write_text("\n".join(sorted(needed_wikibr)) + "\n", "utf-8")
    print(f"Недостающих картинок wikibr.pl: {len(needed_wikibr)} (scraper/source/needed_wikibr.txt)")


if __name__ == "__main__":
    main()
