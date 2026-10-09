#!/usr/bin/env python3
"""Собирает разделы вики из базы сайта (scraper/source/anteikuDB.json).

    python scraper/build.py

Создаёт data/<раздел>.js (+ .json) и scraper/source/needed_images.txt —
картинки, на которые ссылается вики, но которых ещё нет в data/raresImg
(их докачивает: python scraper/fetch_db.py --browser firefox --needed).
"""

import ast
import html as H
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
            color = m.group(1) if m else (t.get("color") if t.name == "font" else None)
            if t.name == "font":
                t.name = "span"
            cls = color_class(color) if color else None
            if cls:
                attrs["class"] = cls
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
    "time": "Респаун", "arenaAsp": "Аспект", "powerG": "Сила (PvE)", "rang": "Ранг",
    "vampbonusM": "Мощь / Знание / Здоровье [ур. 1]", "vampbonusF": "Ловкость / Сила / Здоровье [ур. 1]",
    "orbname": "Эффект", "upgradeLvl": "Улучшение за уровень", "maxUpgrade": "Макс. улучшение",
    "nSlvl": "Уровень", "bossCt": "Кол-во", "touches": "Касания",
}
# Поля, которые выводятся отдельными HTML-блоками, а не строкой таблицы.
BLOCK_LABELS = {
    "drop": "Дроп", "dropdB": "Дроп", "bdrop": "Дроп", "bonus": "Бонус", "setName": "Комплект", "setBonus": "Бонус комплекта",
    "owner": "Где взять", "cenap": "Цена", "skills": "Навыки", "skillsB": "Навыки", "skins": "Скины",
    "team": "Команда", "teamB": "Команда", "morfs": "Образы",
    "reqB": "Требования", "petsk": "Навыки питомца", "dopbonus": "Доп. бонус", "vycup": "Выкуп",
}
SKIP = {"id", "idType", "idClass", "idCatalog", "img", "imgM", "img1", "navigation", "stats", "coordId",
        "map", "linkPage", "linkPagePL", "linkPageEN", "pageName", "mobScenar", "videoB", "mId",
        "titlePL", "titleEN", "descrPL", "descrEN", "orbnamePL", "orbnameEN", "otstup", "morf",
        "bliz", "dal", "mental", "attacks", "star", "orbs", "oskolki", "upgP", "rangp", "lvl",
        "trebLvl", "nSlvl", "p100", "p90", "p70", "zonesB", "areaMap", "mapa", "modif", "suborb",
        "biorb", "magniorb", "arhiorb", "descr3", "bossDrop", "bossCt", "reqB", "upgradeS", "typeG"}
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


ROMAN = re.compile(r"^(I|II|III|IV|V|VI|VII)$")


def is_triplet(v):
    """['рус', 'pol', 'eng'] — одно значение на трёх языках."""
    return (isinstance(v, list) and len(v) == 3 and all(isinstance(x, str) for x in v)
            and re.search(r"[а-яё]", v[0], re.I) and not re.search(r"[а-яё]", v[1] + v[2], re.I))


def ru_only(v):
    """Из многоязычных значений базы оставляет только русское."""
    if isinstance(v, str) and v.startswith("{'ru'"):
        try:
            v = ast.literal_eval(v)
        except (ValueError, SyntaxError):
            return v
    if isinstance(v, dict):
        if "ru" in v and set(v) <= {"ru", "pl", "en"}:
            return ru_only(v["ru"])
        return {k: ru_only(x) for k, x in v.items()}
    if isinstance(v, list):
        if is_triplet(v):
            return v[0]
        return [ru_only(x) for x in v]
    return v


def skill_table(rows):
    """upgradeS: строки уровней, затем заголовки (ru, pl, en) и примечания-тройки."""
    data = [r for r in rows if isinstance(r, list) and r and ROMAN.match(str(r[0]))]
    rest = [r for r in rows if isinstance(r, list) and r not in data]
    notes = [r[0] for r in rest if is_triplet(r)]
    heads = [r for r in rest if not is_triplet(r)]
    head = heads[0] if heads else []
    html = ""
    if data:
        th = "".join(f"<th>{str(h).strip().rstrip(':').strip()}</th>" for h in head)
        trs = "".join("<tr>" + "".join(f"<td>{fmt(x)}</td>" for x in r) + "</tr>" for r in data)
        html = f'<div class="tscroll"><table class="wb skill">{"<tr>" + th + "</tr>" if th else ""}{trs}</table></div>'
    return html, notes


def map_routes(o):
    """areaMap/coordId -> [(маршрут из id карт, точки на последней карте)].

    Плоский список — один маршрут, вложенный — несколько мест. На промежуточных картах
    координаты xS/yS — это переход на следующую карту, на последней x/y — само место.
    """
    areas, coords = o.get("areaMap"), o.get("coordId")
    if not isinstance(areas, list) or not areas:
        return []
    nested = any(isinstance(a, list) for a in areas)
    routes = [a if isinstance(a, list) else [a] for a in areas] if nested else [areas]
    if not isinstance(coords, list):
        coords = []
    cset = coords if nested else [coords]
    out = []
    for i, r in enumerate(routes):
        r = [m for m in r if isinstance(m, str)]
        if not r:
            continue
        cs = cset[i] if i < len(cset) and isinstance(cset[i], list) else []
        tail = cs[len(r) - 1:] if len(cs) >= len(r) else cs[-1:]
        pts = []
        for c in tail:
            for d in (c if isinstance(c, list) else [c]):
                if isinstance(d, dict) and "x" in d:
                    pts.append(d)
        out.append((r, pts))
    return out


def build_entry(o, section, category):
    o = {k: (v if k == "upgradeS" else ru_only(v)) for k, v in o.items()}
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

    mapa = o.get("mapa")
    if isinstance(mapa, str) and mapa.strip() and mapa.strip() != "-":
        fields.append(["Расположение", text_of(mapa)])
    routes = map_routes(o)
    if routes:
        def mlink(m, bold=False):
            t = MAP_NAMES.get(m, m)
            return f'<span data-maps="{m}">{f"<b>{t}</b>" if bold else t}</span>'
        items, seen = [], set()
        for route, _ in routes:
            if tuple(route) in seen:
                continue
            seen.add(tuple(route))
            path = f' <small>— путь: {" → ".join(mlink(m, i == len(route) - 1) for i, m in enumerate(route))}</small>' \
                if len(route) > 1 else ""
            items.append(f"<li>{mlink(route[-1], True)}{path}</li>")
        blocks.append({"title": "Как добраться" if section == "mobs" else "Где найти",
                       "html": '<ul class="plain-list">' + "".join(items) + "</ul>"})

    if isinstance(o.get("upgradeS"), list):
        table, notes = skill_table(o["upgradeS"])
        if notes:
            descr_parts.append((99, "<br>".join(notes)))
        if table:
            blocks.append({"title": "Уровни навыка", "html": table})

    descr = " <br>".join(clean_html(v) for _, v in sorted(descr_parts, key=lambda x: x[0]) if clean_html(v))
    if descr:
        blocks.insert(0, {"title": "Описание", "html": descr})

    model = model_of(o)
    attacks = None
    if section == "mobs" and any(o.get(k) == "+" for k in ("bliz", "dal", "mental", "attacks")):
        attacks = {"b": o.get("bliz") == "+", "d": o.get("dal") == "+", "m": o.get("mental") == "+"}
    return {
        "attacks": attacks,
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


ATK_IMG = re.compile(r"Strefa_ataku_(fizyczna|dystansowe|dystans|mentalne)_(tak|nie)")
ATK_KEY = {"fizyczna": "b", "dystansowe": "d", "dystans": "d", "mentalne": "m"}


ATK_NAMES = (("b", "Ближние"), ("d", "Дальние"), ("m", "Ментальные"))


def atk_html(a):
    return '<span class="atk">' + "".join(
        f'<i class="atk-{k} {"on" if a.get(k) else "off"}" title="{n} атаки: {"да" if a.get(k) else "нет"}"></i>'
        for k, n in ATK_NAMES) + "</span>"


def add_attacks():
    """Типы атак мобов: из базы, иначе из блока «Зоны атаки» второй вики (он заменяется значками)."""
    for _, entries in SECTIONS_OUT.values():
        for e in entries:
            keep = []
            for b in e["blocks"]:
                if not ATK_IMG.search(b["html"]):
                    keep.append(b)
                    continue
                out = []
                for part in re.split(r"<hr/?>", b["html"]):
                    if not ATK_IMG.search(part):
                        if text_of(part) or "<img" in part:
                            out.append(part)
                        continue
                    a = {ATK_KEY[k]: v == "tak" for k, v in ATK_IMG.findall(part)}
                    if b["title"] == "Зоны атаки" and (not e.get("attacks") or e["attacks"] == a):
                        e["attacks"] = a
                        continue
                    out.append(atk_html(a))
                if out:
                    b["html"] = "<hr>".join(out)
                    keep.append(b)
            e["blocks"] = keep
            if not e.get("attacks"):
                e.pop("attacks", None)


# ---------- мобы: статистика по сложностям, умения, локации ----------

PATH_KEYS = (("познания", "e"), ("приключения", "n"), ("испытания", "h"))
STAT_LABELS = ("Уровень", "Здоровье", "Мана", "Выносливость")


def nkey(t):
    t = re.sub(r"<[^>]+>", " ", t or "").lower().replace("ё", "е")
    return re.sub(r"\s+", " ", re.sub(r"[,.;:!?«»\"()]", " ", t)).strip()


def stats_by_path(html):
    """Таблица «Статистика» второй вики -> {"Уровень": {"e": "20", "n": "30", "h": "40"}, ...}."""
    soup = BeautifulSoup(html, "html.parser")
    tbl = soup.find("table")
    if not tbl:
        return {}
    rows = tbl.find_all("tr")
    keys = []
    for c in rows[0].find_all(["td", "th"], recursive=False) if rows else []:
        title = " ".join(i.get("title", "") for i in c.find_all("img")) + " " + c.get_text(" ")
        keys.append(next((k for w, k in PATH_KEYS if w in title.lower()), None))
    out = {}
    for r in rows[1:]:
        for key, c in zip(keys, r.find_all(["td", "th"], recursive=False)):
            if not key:
                continue
            for label, val in re.findall(r"(Уровень|Здоровье|Мана|Выносливость)\s*:\s*([\d\s]+)", c.get_text(" ")):
                v = re.sub(r"\s+", "", val)
                if v:
                    out.setdefault(label, {})[key] = v
    return out


def split_names(html):
    parts = re.split(r"<br/?>|</?p>|</?div[^>]*>|</?li>|,\s*", html or "")
    return [t for t in (re.sub(r"\s+", " ", text_of(x)).strip(" -—") for x in parts) if t and t != "-"]


def tidy_mobs(maps):
    """Статистику по путям — в значения по сложностям, умения — ссылками, локации — одним блоком для всех."""
    mobs = SECTIONS_OUT["mobs"][1]
    guides = SECTIONS_OUT.get("guides", ([], []))[1]
    by_id = {e["id"]: e for _, ents in SECTIONS_OUT.values() for e in ents}
    skills = {nkey(e["name"]): e["id"] for e in SECTIONS_OUT["skills"][1]}
    skill_icon = {e["id"]: e.get("icon") for e in SECTIONS_OUT["skills"][1]}
    map_exact, map_prefix = {}, {}
    for m in maps:
        if m.get("unnamed"):
            continue
        k = nkey(m["name"])
        map_exact.setdefault(k, m["id"])
        map_prefix.setdefault(nkey(re.split(r"\s+[-—–]\s+", m["name"])[0]), m["id"])
    points = {}
    for m in maps:
        for p in m["points"]:
            points.setdefault(p["id"], []).append(m["id"])
    articles = {nkey(a["name"]): a["id"] for a in guides if a["category"] in ("locations", "instances")}
    art_refs = {}
    for a in guides:
        if a["category"] in ("locations", "instances"):
            for b in a["blocks"]:
                for i in re.findall(r'data-items="([^"]+)"', b["html"]):
                    art_refs.setdefault(i, []).append(a["name"])
    # Таблица респауна: моб -> локации.
    # Таблицы статей с колонкой «Локация» (респаун, элита, боссы…): моб -> локации.
    respawn = {}
    for a in guides:
        for blk in a["blocks"]:
            for tbl in re.findall(r"<table[^>]*>(.*?)</table>", blk["html"], re.S):
                col = None
                for row in re.findall(r"<tr[^>]*>(.*?)</tr>", tbl, re.S):
                    cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)
                    heads = [nkey(c) for c in cells]
                    if any(h in ("локация", "локации", "местонахождение") for h in heads):
                        col = next(i for i, h in enumerate(heads) if h in ("локация", "локации", "местонахождение"))
                        continue
                    ids = re.findall(r'data-items="([^"]+)"', row)
                    if col is not None and ids and len(cells) > col:
                        respawn.setdefault(ids[0], []).extend(split_names(cells[col]))
    # Отряды боссов и чемпионов: участник -> вожак.
    owners = {}
    for sec in ("bossMain", "champsMain"):
        for o in DB.get(sec, {}).values():
            team = json.dumps([o.get("teamB"), o.get("team")], ensure_ascii=False)
            for i in dict.fromkeys(re.findall(r'data-items=\\"([^"\\]+)', team)):
                if i != o["id"]:
                    owners.setdefault(i, []).append(o["id"])

    def link(name):
        k = nkey(name)
        if k in map_exact:
            return f'<span data-maps="{map_exact[k]}">{H.escape(name)}</span>'
        if k in articles:
            return f'<span data-items="{articles[k]}">{H.escape(name)}</span>'
        if k in map_prefix:
            return f'<span data-maps="{map_prefix[k]}">{H.escape(name)}</span>'
        return H.escape(name)

    names_of, stats_moved, skill_links = {}, 0, 0
    for e in mobs:
        # 1) Статистика по путям -> значения по сложностям; сами таблицы не нужны (есть полосы и поля).
        st = next((b for b in e["blocks"] if b["title"] == "Статистика"), None)
        if st:
            vals = stats_by_path(st["html"])
            lvl = vals.get("Уровень", {})
            if len(lvl) >= 2 and str(lvl.get("n", e.get("level"))) == str(e.get("level")):
                for label in STAT_LABELS:
                    v = vals.get(label)
                    f = next((f for f in e["fields"] if f[0] == label), None)
                    if v and len(set(v.values())) > 1 and f and not isinstance(f[1], dict):
                        f[1] = {k: fmt(int(v[k])) if k in v else "-" for _, k in PATH_KEYS}
                        stats_moved += 1
        e["blocks"] = [b for b in e["blocks"] if not b["title"].endswith("Статистика")
                       and (text_of(b["html"]).strip(" -—") or "<img" in b["html"])]
        # Путь сложности и аспект (механика Насыщения) — полями, а не отдельными блоками.
        for b in [b for b in e["blocks"] if b["title"] in ("Путь", "Аспект")]:
            val = (split_names(b["html"]) or [""])[-1]
            label = "Путь сложности" if b["title"] == "Путь" else "Аспект"
            if val and not any(f[0] == label for f in e["fields"]):
                e["fields"].append([label, val])
            e["blocks"].remove(b)
        # 2) Умения — ссылками на раздел «Навыки».
        for b in e["blocks"]:
            if not b["title"].endswith("Умения") or "<td" not in b["html"]:
                continue
            items = []
            for cell in re.findall(r"<td[^>]*>(.*?)</td>", b["html"], re.S):
                parts = re.split(r"<p>|<br/?>", cell, maxsplit=1)
                name = text_of(parts[0])
                if not name or name == "-":
                    continue
                note = ", ".join(split_names(parts[1])) if len(parts) > 1 else ""
                sid = skills.get(nkey(name))
                skill_links += bool(sid)
                icon = f'<img class="skill-ico" data-items="{sid}" src="{skill_icon[sid]}" title="{H.escape(name)}"/> ' \
                    if sid and skill_icon.get(sid) else ""
                ref = icon + (f'<span data-items="{sid}">{H.escape(name)}</span>' if sid else H.escape(name))
                items.append(f"<li>{ref}{f' <small>— {H.escape(note.lower())}</small>' if note else ''}</li>")
            if items:
                b["html"] = '<ul class="plain-list">' + "".join(items) + "</ul>"
        # 3) Локации из всех источников.
        names = []
        for f in [f for f in e["fields"] if f[0] == "Расположение"]:
            names += split_names(str(f[1]))
            e["fields"].remove(f)
        for b in [b for b in e["blocks"] if b["title"].endswith("Локация")]:
            names += split_names(b["html"])
            e["blocks"].remove(b)
        names += respawn.get(e["id"], []) + art_refs.get(e["id"], [])
        names += [MAP_NAMES.get(m, m) for m in points.get(e["id"], [])]
        seen, uniq = set(), []
        for n in names:
            if nkey(n) and nkey(n) not in seen:
                seen.add(nkey(n))
                uniq.append(n)
        names_of[e["id"]] = uniq
    # Упоминание по названию (без ссылки) в статьях о локациях и инстансах.
    art_text = [(a["name"], nkey(" ".join(b["html"] for b in a["blocks"]))) for a in guides
                if a["category"] in ("locations", "instances")]
    for e in mobs:
        n = nkey(e["name"])
        if names_of[e["id"]] or len(n) < 4:
            continue
        rx = re.compile(r"(?<![а-яa-z])" + re.escape(n) + r"(?![а-яa-z])")
        names_of[e["id"]] = list(dict.fromkeys(an for an, t in art_text if rx.search(t)))
    # Сопартийцы из блоков «Команда»: кто в одной группе — тот там же.
    mates = {}
    for e in mobs:
        for b in e["blocks"]:
            if b["title"].endswith("Команда"):
                for i in set(re.findall(r'data-items="([^"]+)"', b["html"])) - {e["id"]}:
                    mates.setdefault(i, set()).add(e["id"])
                    mates.setdefault(e["id"], set()).add(i)
    located = 0
    for e in mobs:
        lines = [f"<li>{link(n)}</li>" for n in names_of[e["id"]]]
        if not lines:
            with_loc = [m for m in sorted(mates.get(e["id"], ())) if names_of.get(m)]
            if with_loc:
                lines = [f"<li>{link(n)}</li>" for n in dict.fromkeys(n for m in with_loc for n in names_of[m])]
                lines.append("<li><small>в одной группе с: " + ", ".join(
                    f'<span data-items="{m}">{H.escape(by_id[m]["name"])}</span>' for m in with_loc[:5]) + "</small></li>")
        team = []
        for oid in dict.fromkeys(owners.get(e["id"], [])):
            if oid in by_id:
                where = names_of.get(oid) or []
                team.append(f'<span data-items="{oid}">{H.escape(by_id[oid]["name"])}</span>'
                            + (f" ({', '.join(link(n) for n in where[:3])})" if where else ""))
        html = ""
        if lines:
            html += '<ul class="plain-list">' + "".join(lines) + "</ul>"
        if team:
            html += "<p>В отряде: " + ", ".join(team) + "</p>"
        if html:
            located += 1
            e["blocks"].insert(0, {"title": "Локация", "html": html})
    print(f"Мобы: локация у {located} из {len(mobs)}, статистика по сложностям у {stats_moved} полей, "
          f"связанных умений: {skill_links}")


CLASS_ARTICLES = {"wb_barbarzynca": "Варвар", "wb_druid": "Друид", "wb_lucznik": "Лучник", "wb_mag_ognia": "Огненный маг",
                  "wb_rycerz": "Рыцарь", "wb_sheed": "Шид", "wb_voodoo": "Вуду", "wb_umiejetnosci_specjalne": "Особые"}


def tag_skills():
    """Навыкам — класс (по статьям о классах) и требуемый уровень персонажа для каждого уровня навыка."""
    skills = SECTIONS_OUT["skills"][1]
    by_name = {nkey(e["name"]): e for e in skills}
    guides = {a["id"]: a for a in SECTIONS_OUT.get("guides", ([], []))[1]}
    for aid, cls in CLASS_ARTICLES.items():
        a = guides.get(aid)
        if not a:
            continue
        html = " ".join(b["html"] for b in a["blocks"])
        parts = re.split(r"<h3>(.*?)</h3>", html)
        for order, (h, body) in enumerate(zip(parts[1::2], parts[2::2])):
            e = by_name.get(nkey(h))
            if not e or "skillClass" in e:
                continue
            e["skillClass"], e["skillOrder"] = cls, order
            # Требуемые уровни — из таблицы статьи (в основной базе у особых навыков они неверные).
            req = []
            for row in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
                cells = [text_of(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S)]
                if len(cells) >= 2 and re.match(r"(Ученик|Адепт|Мастер)\s+[IVX]+$", cells[0]) and cells[1].isdigit():
                    req.append(int(cells[1]))
            if req and cls == "Особые":  # у классовых навыков таблицы вики сдвинуты на 1, верна основная база
                e["skillReq"] = req
    for e in skills:
        o = DB["skillsMain"].get(e["id"], {})
        rows = [r for r in o.get("upgradeS") or [] if isinstance(r, list) and r and ROMAN.match(str(r[0]))]
        req = [int(r[1]) for r in rows if str(r[1]).isdigit()]
        if req and "skillReq" not in e:
            e["skillReq"] = req


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
    """Карты с картинками, порталами и точками объектов (для data/maps.js)."""
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
        for route, pts in map_routes(o):
            for c in pts:
                add_point(route[-1], o.get("id"), c)
    for mp in maps.values():
        for p in mp["portals"]:
            p["name"] = MAP_NAMES.get(p["to"], p["to"])
    for mp in maps.values():
        # У части карт на сайте вместо имени заглушка — подписываем номером и уводим в конец.
        if mp["name"] in ("Название", mp["id"]):
            mp["name"] = f"Безымянная локация №{mp['id'][1:]}"
            mp["unnamed"] = True
    return sorted(maps.values(), key=lambda x: (bool(x.get("unnamed")), int(re.sub(r"\D", "", x["id"]) or 0)))


def write_maps(out):
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


class Untranslated(Exception):
    pass


def tr_strict(text):
    """Перевод фрагмента целиком или исключение — чтобы не смешивать языки в одной фразе."""
    t = tr_core(text.strip())
    if t is None:
        raise Untranslated(text)
    return t


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
            m = re.match(r"^(\s*)(.*?)(\s*\(.*\))?$", part)
            name = m.group(2)
            t = tr_core(name) if LATIN.search(name) else name
            if t is None:
                untranslated[name] += 1
            paren = m.group(3) or ""
            pm = re.match(r"^(\s*\()(.*)(\))$", paren)
            if pm and LATIN.search(pm.group(2)):
                pt = tr_core(pm.group(2))
                if pt is None:
                    untranslated[pm.group(2)] += 1
                else:
                    paren = pm.group(1) + pt + pm.group(3)
            out.append(m.group(1) + (t if t is not None else name) + paren)
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
    (re.compile(r"^Poziom : ([\d\s]+) Ranga : (\d+) Punkty życia : ([\d\s]+) Mana : ([\d\s]+) Kondycja : ([\d\s]+)$"),
     lambda m: f"Уровень: {m.group(1).strip()}, ранг: {m.group(2)}, здоровье: {m.group(3).strip()}, "
               f"мана: {m.group(4).strip()}, выносливость: {m.group(5).strip()}"),
    (re.compile(r"^Specyfik umożliwiający kontrolę mocy podczas ulepszania sprzętu rangi ([IVX\-]+)\.$"),
     lambda m: f"Средство для контроля силы при улучшении снаряжения ранга {m.group(1).replace('-', '–')}."),
    (re.compile(r"^Składnik używany do produkcji (.+?)\. Wykonuje (?:ją|go|je) (.+?) w (.+?)\.$"),
     lambda m: f"Ингредиент для изготовления: {tr_strict(m.group(1))}. Изготавливает {tr_names(m.group(2))} — {tr_strict(m.group(3))}."),
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
            try:
                return fn(m)
            except Untranslated:
                return None
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

    def convert(html, self_id=None):
        def link(m):
            tid = title_to_id.get(m.group(1)) or title_to_id.get(redirects.get(m.group(1), ""))
            return f'data-items="{tid}"' if tid else ""
        html = re.sub(r'data-wikibr="([^"]+)"', link, html)
        html = re.sub(r'data-wikibr-img="([^"]+)"', lambda m: f'src="{wb_img(m.group(1))}"', html)
        return tidy_article(tr_html(html), self_id)

    def merge(e, p):
        """Блоки с тем же заголовком дополняются, новые — добавляются; простые поля — в таблицу."""
        have_fields = {k for k, _ in e["fields"]}
        for k, v in p.get("fields", []):
            label = tr_text(k).strip()
            if "<" in v:
                add_block(e, label, convert(v, e["id"]))
            elif label not in have_fields:
                e["fields"].append([label, tr_text(v).strip()])
                have_fields.add(label)
        for b in p.get("blocks", []):
            add_block(e, tr_text(b["title"]).strip(), convert(b["html"], e["id"]))

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
    # Статьи без содержимого (страницы-заглушки) не нужны.
    write("guides", cats, [e for _, e in new_entries if any(text_of(b["html"]) for b in e["blocks"])])
    todo = [{"pl": k, "count": n} for k, n in untranslated.most_common()]
    (SRC / "translate_todo.json").write_text(json.dumps(todo, ensure_ascii=False, indent=0), "utf-8")
    print(f"Вторая вики: дополнено записей {sum(len(c) for _, c in matched)}, новых статей {len(new_entries)}; "
          f"непереведённых фрагментов: {len(untranslated)} (scraper/source/translate_todo.json)")


# ---------- оформление статей второй вики ----------

NAMED_COLORS = {"red": "#ff0000", "green": "#008000", "lime": "#00ff00", "yellow": "#ffff00", "orange": "#ffa500",
                "blue": "#0000ff", "cyan": "#00ffff", "aqua": "#00ffff", "purple": "#800080", "violet": "#ee82ee",
                "white": "#ffffff", "black": "#000000", "gold": "#ffd700", "pink": "#ffc0cb", "gray": "#808080",
                "grey": "#808080", "silver": "#c0c0c0", "magenta": "#ff00ff", "fuchsia": "#ff00ff"}


def color_class(c):
    """Цвет из разметки -> класс палитры сайта (читаемой в обеих темах) или None."""
    import colorsys
    c = NAMED_COLORS.get(c.lower(), c)
    m = re.fullmatch(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})", c)
    if not m:
        return None
    h = m.group(1)
    if len(h) == 3:
        h = "".join(x * 2 for x in h)
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    hue, light, sat = colorsys.rgb_to_hls(r, g, b)
    if sat < 0.25 or light < 0.15 or light > 0.93:
        return None  # серые, белый, чёрный — это просто цвет текста
    deg = hue * 360
    for limit, name in ((15, "red"), (40, "orange"), (68, "yellow"), (165, "green"), (200, "cyan"),
                        (255, "blue"), (330, "purple"), (361, "red")):
        if deg < limit:
            return "c-" + name


def tidy_article(html, self_id=None):
    """Приводит HTML статьи к аккуратному виду: без центровки, пустых обёрток и случайных цветов."""
    soup = BeautifulSoup(html, "html.parser")
    for t in soup.find_all(["center", "font"]):
        t.unwrap()
    for t in soup.find_all(True):
        if t.get("data-items") and t["data-items"] == self_id:
            del t["data-items"]
        style = t.get("style", "")
        if style:
            m = re.search(r"color:\s*([#\w]+)", style)
            cls = color_class(m.group(1)) if m else None
            del t["style"]
            if cls:
                t["class"] = (t.get("class") or []) + [cls]
    # Обёртки-div вокруг абзацев и таблиц не нужны (на сайте div в блоках строчный).
    for t in soup.find_all("div"):
        if not t.get("class") and t.find(["p", "h1", "h2", "h3", "h4", "ul", "ol", "table", "div"], recursive=False):
            t.unwrap()
    # Заголовки: только текст, без декоративных картинок-полосок.
    for t in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        text = re.sub(r"\s+", " ", t.get_text(" ")).strip()
        if not text:
            t.decompose()
            continue
        t.clear()
        t.string = text
        t.name = "h4" if t.name in ("h4", "h5", "h6") else "h3"
    # Пустые обёртки.
    changed = True
    while changed:
        changed = False
        for t in soup.find_all(["span", "p", "b", "i", "strong", "em", "div", "small", "u"]):
            if not t.get_text(strip=True) and not t.find(["img", "table", "hr"]):
                if t.find("br") and t.name != "p":
                    t.unwrap()  # обёртка вокруг переноса строки: перенос оставляем
                else:
                    t.decompose()
                changed = True
            elif t.name == "span" and not t.attrs:
                t.unwrap()
                changed = True
    # Таблицы: содержимое вне строк — перед таблицей; сама таблица — в прокручиваемой обёртке.
    for tbl in soup.find_all("table"):
        for ch in list(tbl.children):
            if isinstance(ch, Tag) and ch.name not in ("tbody", "tr", "thead", "caption"):
                tbl.insert_before(ch.extract())
            elif isinstance(ch, NavigableString) and ch.strip():
                tbl.insert_before(ch.extract())
        if not tbl.find(["td", "th"]):
            tbl.decompose()
            continue
        # Строки из одной ячейки во всю ширину («Тип урона: Магические») — списком над таблицей.
        rows = tbl.find_all("tr")
        width = max((sum(int(c.get("colspan", 1) or 1) for c in r.find_all(["td", "th"], recursive=False))
                     for r in rows), default=1)
        kv = []
        for r in rows:
            cells = r.find_all(["td", "th"], recursive=False)
            if width > 2 and len(cells) == 1 and int(cells[0].get("colspan", 1) or 1) >= width \
                    and len(cells[0].get_text(strip=True)) < 160 and not cells[0].find("table"):
                kv.append(cells[0])
                r.extract()
            else:
                break
        prev = tbl.find_previous(["h3", "h4"])
        if kv and prev is not None and kv[0].get_text(" ", strip=True) == prev.get_text(" ", strip=True):
            kv = kv[1:]  # повтор заголовка раздела
        if kv:
            box = soup.new_tag("div", attrs={"class": "kv"})
            for c in kv:
                c.name = "div"
                c.attrs = {}
                box.append(c)
            tbl.insert_before(box)
        if not tbl.find(["td", "th"]):
            tbl.decompose()
            continue
        tbl["class"] = (tbl.get("class") or []) + ["art"]
        if not (tbl.parent and "tscroll" in (tbl.parent.get("class") or [])):
            wrap = soup.new_tag("div", attrs={"class": "tscroll"})
            tbl.wrap(wrap)
    for t in soup.find_all(["b", "strong"]):
        if t.parent is soup and len(t.get_text(strip=True)) > 90:
            t.name = "p"
            t["class"] = ["lead"]
    for img in soup.find_all("img"):
        par = img.parent
        if par is not None and par.name in ("p", "[document]") and not img.find_parent("table") \
                and not par.get_text(strip=True) and len(par.find_all("img")) == 1 and not img.get("data-items"):
            img["class"] = ["big"]
    out = str(soup)
    out = re.sub(r"(\s*<br/?>\s*){2,}", "<br/>", out)
    out = re.sub(r"(<(h3|h4|p|div|ul|ol|table)[^>]*>)\s*<br/?>", r"\1", out)
    out = re.sub(r"<br/?>\s*(</?(h3|h4|p|div|ul|ol|li|table|tr|td|th)\b)", r"\1", out)
    out = re.sub(r"\s{2,}", " ", out).strip()
    out = re.sub(r"^(<br/?>\s*)+|(<br/?>\s*)+$", "", out)
    return out


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
    add_attacks()
    maps = build_maps()
    tidy_mobs(maps)
    tag_skills()
    add_backrefs()
    for sid, (cats, entries) in SECTIONS_OUT.items():
        write_out(sid, cats, entries)
    import static_pages
    static_pages.generate(SECTIONS_OUT)
    write_maps(maps)
    (SRC / "needed_images.txt").write_text("\n".join(sorted(needed_images)) + "\n", "utf-8")
    print(f"Недостающих картинок: {len(needed_images)} (scraper/source/needed_images.txt)")
    (SRC / "needed_wikibr.txt").write_text("\n".join(sorted(needed_wikibr)) + "\n", "utf-8")
    print(f"Недостающих картинок wikibr.pl: {len(needed_wikibr)} (scraper/source/needed_wikibr.txt)")


if __name__ == "__main__":
    main()
