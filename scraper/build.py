#!/usr/bin/env python3
"""Собирает разделы вики из базы сайта (scraper/source/anteikuDB.json).

    python scraper/build.py

Создаёт data/<раздел>.js (+ .json) и scraper/source/needed_images.txt —
картинки, на которые ссылается вики, но которых ещё нет в data/raresImg
(их докачивает: python scraper/fetch_db.py --browser firefox --needed).
"""

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
    "team": "Команда", "teamB": "Команда", "morfs": "Образы", "forCrt": "Используется для создания",
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
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, int) and abs(v) >= 10000:
        return f"{v:,}".replace(",", " ")
    return str(v)


def diff_value(v):
    """{'e':..,'n':..,'h':..} -> '1100' или '900 / 1100 / 1500 (лёгк./норм./тяжел.)'."""
    if not isinstance(v, dict):
        return fmt(v)
    vals = [v.get(k) for k, _ in DIFF if k in v]
    vals = [x for x in vals if x not in (None, "", "-")]
    if not vals:
        return ""
    if len(set(map(str, vals))) == 1:
        return fmt(vals[0])
    return " / ".join(fmt(v.get(k, "-")) for k, _ in DIFF) + " (" + "/".join(n for _, n in DIFF) + ")"


def ref_html(oid):
    """Иконка-ссылка на объект базы по его id."""
    for sec in DB.values():
        if isinstance(sec, dict) and isinstance(sec.get(oid), dict):
            o = sec[oid]
            return f'<img data-items="{oid}" src="{icon_of(o)}" title="{o.get("title", oid)}">'
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
    if isinstance(lvl, dict):
        lvl = lvl.get("n") or next((x for x in lvl.values() if isinstance(x, (int, float))), None)
    if isinstance(lvl, str) and lvl.isdigit():
        lvl = int(lvl)
    if isinstance(lvl, (int, float)) and lvl:
        level = int(lvl)
        fields.append(["Уровень" if section in ("mobs", "pets") and "lvl" in o else "Требуемый уровень", fmt(level)])

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

    descr_parts = []
    for k, v in o.items():
        if k in SKIP or k.startswith(("title", "otstup")) or v in (None, "", [], {}):
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

    if isinstance(o.get("modif"), dict) and o["modif"]:
        items = []
        for _, pair in o["modif"].items():
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
        names = list(dict.fromkeys(MAP_NAMES.get(m, m) for m in flat if isinstance(m, str)))
        blocks.append({"title": "Путь по картам" if section == "mobs" else "Где найти",
                       "html": " → ".join(names) if section == "mobs" else ", ".join(names)})

    descr = " <br>".join(clean_html(v) for _, v in sorted(descr_parts, key=lambda x: x[0]) if clean_html(v))
    if descr:
        blocks.insert(0, {"title": "Описание", "html": descr})

    model = model_of(o)
    return {
        "id": o["id"],
        "category": category,
        "name": title,
        "nameEN": o.get("titleEN", ""),
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


def write(sid, cats, entries):
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
    write("equipment", *equipment())
    write("pets", *by_class("petsMain", PET_CATS, "pets"))
    write("mobs", *mobs())
    write("items", *items())
    write("npc", [], [build_entry(o, "npc", "_") for o in DB["npcMain"].values()])
    write("skills", [], [build_entry(o, "skills", "_") for o in DB["skillsMain"].values()])
    (SRC / "needed_images.txt").write_text("\n".join(sorted(needed_images)) + "\n", "utf-8")
    print(f"Недостающих картинок: {len(needed_images)} (scraper/source/needed_images.txt)")


if __name__ == "__main__":
    main()
