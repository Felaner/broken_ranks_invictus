"""Статические страницы для поисковиков: e/<id>.html на каждую запись, e/index.html, sitemap.xml, robots.txt.

Интерактивная вики (index.html) — одна страница с адресами через «#», которые поисковики не индексируют.
Поэтому для каждой записи генерируется обычная HTML-страница с тем же содержимым и ссылкой в вики.
"""
import html as H
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "e"
# Адрес опубликованного сайта (со слешем в конце). Его же нужно указать в Яндекс.Вебмастере и Search Console.
SITE_URL = "https://felaner.github.io/broken_ranks_invictus/"
SITE_NAME = "Broken Ranks Fandom Wiki"

SEC_TITLES = {"equipment": "Экипировка", "pets": "Питомцы", "mobs": "Противники", "items": "Предметы",
              "npc": "НПС", "skills": "Навыки", "guides": "Статьи"}
SEC_ORDER = list(SEC_TITLES)
DIFF = (("e", "лёгк."), ("n", "норм."), ("h", "тяжел."))
ATK = (("b", "Ближние"), ("d", "Дальние"), ("m", "Ментальные"))


def esc(s):
    return H.escape(str(s), quote=True)


def fname(eid):
    return re.sub(r"[^A-Za-z0-9_.-]", "_", eid) + ".html"


def fv(v):
    """Значение поля: для разных сложностей — «лёгк. 900 / норм. 1100 / тяжел. 1500»."""
    if isinstance(v, dict):
        return " / ".join(f"{n} {v[k]}" for k, n in DIFF if v.get(k) not in (None, "", "-"))
    return str(v)


def text_of(html):
    t = re.sub(r"<[^>]+>", " ", html or "")
    return re.sub(r"\s+", " ", H.unescape(t)).strip()


def page(title, desc, canonical, body, image=None, depth=1):
    up = "../" * depth
    og_img = f'<meta property="og:image" content="{esc(SITE_URL + image)}">' if image else ""
    return f"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{esc(canonical)}">
<meta property="og:type" content="article">
<meta property="og:site_name" content="{SITE_NAME}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{esc(canonical)}">
{og_img}
<link rel="stylesheet" href="{up}assets/style.css">
<script>try{{var t=JSON.parse(localStorage.getItem("brwiki:theme"));if(t)document.documentElement.dataset.theme=t}}catch(e){{}}</script>
</head>
<body class="static">
<header class="topbar">
  <a class="logo" href="{up}index.html"><span class="logo-mark">⚔</span>
    <span class="logo-text">Broken Ranks <b>Fandom Wiki</b></span></a>
  <nav class="static-nav"><a href="{up}index.html">Интерактивная вики</a> · <a href="{up}e/index.html">Все страницы</a></nav>
</header>
<main class="static-page">
{body}
<footer class="static-foot">Неофициальная фанатская вики по игре Broken Ranks. Не связана с Whitemoon Games и Fandom, Inc.
  Все игровые материалы принадлежат их правообладателям. Идеи и вопросы — в Telegram:
  <a href="https://t.me/felaner" rel="noopener">@felaner</a>. <a href="{up}index.html#/about">О сайте</a></footer>
</main>
<script>
document.querySelectorAll(".block-html img").forEach(function(img){{
  img.loading="lazy";
  img.addEventListener("error",function(){{
    var t=img.getAttribute("title");
    if(t){{var s=document.createElement("span");s.className="img-missing";s.textContent=t;img.replaceWith(s)}}else img.remove();
  }},{{once:true}});
}});
</script>
</body>
</html>
"""


def fix_html(html, known, depth=1):
    """Пути картинок — относительно папки e/, связи data-items — обычные ссылки на страницы."""
    up = "../" * depth
    html = re.sub(r'src="(data/[^"]+)"', lambda m: f'src="{up}{m.group(1)}"', html)

    def link(m):
        tag, eid = m.group(0), m.group(1)
        if eid not in known:
            return tag
        return (f'<a class="ref-link" href="{fname(eid)}" title="{esc(known[eid]["name"])}">{tag}'
                f'<span class="ref-name">{esc(known[eid]["name"])}</span></a>')
    html = re.sub(r'<img[^>]*\bdata-items="([^"]+)"[^>]*/?>', link, html)

    def span(m):
        eid, inner = m.group(2), m.group(3)
        if eid not in known:
            return m.group(0)
        return f'<a href="{fname(eid)}">{inner}</a>'
    html = re.sub(r'<(span|b|i)[^>]*\bdata-items="([^"]+)"[^>]*>(.*?)</\1>', span, html)
    html = re.sub(r'<span data-maps="([^"]+)">(.*?)</span>',
                  lambda m: f'<a href="{up}index.html#/maps/{esc(m.group(1))}">{m.group(2)}</a>', html)
    return html


def describe(e, sec_title, cat_name):
    """Описание для поисковой выдачи (до ~160 символов)."""
    head = f"{e['name']} — {sec_title.lower()}" + (f" ({cat_name.lower()})" if cat_name else "")
    if e.get("level"):
        head += f", {e['level']} уровень"
    parts = [head + ". Broken Ranks."]
    facts = [f"{k}: {fv(v)}" for k, v in e.get("fields", []) if fv(v) and "уровень" not in k.lower()][:4]
    if facts:
        parts.append("; ".join(facts) + ".")
    first = next((text_of(b["html"]) for b in e.get("blocks", []) if text_of(b["html"])), "")
    if first:
        parts.append(first)
    d = " ".join(parts)
    return (d[:157].rsplit(" ", 1)[0] + "…") if len(d) > 160 else d


def entry_page(e, sid, cats, known):
    sec_title = SEC_TITLES.get(sid, sid)
    cat_name = cats.get(e["category"], "")
    kind = f"{sec_title}: {cat_name}" if cat_name else sec_title
    title = f"{e['name']} — {kind}" + (f", {e['level']} ур." if e.get("level") else "") + f" | {SITE_NAME}"
    wiki = f"../index.html#/s/{sid}/{e['category']}?e={e['id']}"
    icon = f'<div class="ico ico-lg"><img src="../{esc(e["icon"])}" alt="{esc(e["name"])}"></div>' \
        if e.get("icon") else ""
    atk = ""
    if e.get("attacks"):
        atk = '<div class="atk-line">Атакует: <span class="atk">' + "".join(
            f'<i class="atk-{k} {"on" if e["attacks"].get(k) else "off"}" title="{n} атаки: '
            f'{"да" if e["attacks"].get(k) else "нет"}"></i>' for k, n in ATK) + "</span> " + ", ".join(
            n.lower() for k, n in ATK if e["attacks"].get(k)) + "</div>"
    crumbs = f'<a href="index.html#{sid}">{esc(sec_title)}</a>' + (f" / {esc(cat_name)}" if cat_name else "")
    body = [f"""<div class="detail-head">{icon}<div>
  <h1>{esc(e['name'])}</h1>
  <div class="crumbs">{crumbs}</div>
  {f'<span class="lvl">Уровень {esc(e["level"])}</span>' if e.get("level") else ""}
  {atk}
</div></div>
<p><a class="static-open" href="{esc(wiki)}">Открыть в интерактивной вики →</a></p>"""]
    if e.get("image"):
        body.append(f'<div class="model"><img src="../{esc(e["image"])}" alt="{esc(e["name"])}"></div>')
    if e.get("fields"):
        body.append('<table class="props">' + "".join(
            f"<tr><th>{esc(k)}</th><td>{esc(fv(v))}</td></tr>" for k, v in e["fields"]) + "</table>")
    for b in e.get("blocks", []):
        t = b.get("title") or ""
        h2 = f"<h2>{esc(t)}</h2>" if t and t != "Статья" else ""
        body.append(f'<section class="block">{h2}<div class="block-html">{fix_html(b["html"], known)}</div></section>')
    for r in e.get("backrefs", []):
        links = ", ".join(f'<a href="{fname(i)}">{esc(known[i]["name"])}</a>' for i in r["ids"] if i in known)
        if links:
            body.append(f'<section class="block"><h2>{esc(r["title"])}</h2><div class="block-html">{links}</div></section>')
    return title, describe(e, sec_title, cat_name), "\n".join(body)


def generate(sections):
    """sections: {sid: (cats, entries)} — то же, что пишется в data/*.js."""
    OUT.mkdir(exist_ok=True)
    for old in OUT.glob("*.html"):
        old.unlink()
    known = {e["id"]: e for _, ents in sections.values() for e in ents}
    urls = [SITE_URL]
    index = []
    for sid in sorted(sections, key=lambda s: SEC_ORDER.index(s) if s in SEC_ORDER else 99):
        cats_list, entries = sections[sid]
        cats = {c["id"]: c["name"] for c in cats_list}
        groups = {}
        for e in entries:
            title, desc, body = entry_page(e, sid, cats, known)
            url = SITE_URL + "e/" + fname(e["id"])
            img = e.get("icon") or None
            (OUT / fname(e["id"])).write_text(page(title, desc, url, body, img), "utf-8")
            urls.append(url)
            groups.setdefault(cats.get(e["category"], ""), []).append(e)
        part = [f'<h2 id="{sid}">{esc(SEC_TITLES.get(sid, sid))} <small>{len(entries)}</small></h2>']
        for cname, ents in groups.items():
            if cname:
                part.append(f"<h3>{esc(cname)}</h3>")
            part.append('<ul class="static-list">' + "".join(
                f'<li><a href="{fname(e["id"])}">{esc(e["name"])}</a></li>'
                for e in sorted(ents, key=lambda x: x["name"])) + "</ul>")
        index.append("\n".join(part))
    total = len(urls) - 1
    body = f"""<h1>Все страницы вики</h1>
<p>Полный список записей ({total}): экипировка, питомцы, противники, предметы, НПС, навыки и статьи.
  Удобнее искать в <a href="../index.html">интерактивной вики</a> — там есть фильтры, сравнение, карты и поиск.</p>
<nav class="static-toc">{" · ".join(f'<a href="#{s}">{esc(SEC_TITLES.get(s, s))}</a>' for s in sections)}</nav>
{"".join(index)}"""
    (OUT / "index.html").write_text(page(f"Все страницы | {SITE_NAME}",
                                         "Список всех записей неофициальной фанатской вики по игре Broken Ranks: "
                                         "экипировка, питомцы, противники, предметы, НПС, навыки и статьи.",
                                         SITE_URL + "e/index.html", body), "utf-8")
    urls.insert(1, SITE_URL + "e/index.html")
    today = date.today().isoformat()
    (ROOT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"<url><loc>{esc(u)}</loc><lastmod>{today}</lastmod></url>\n" for u in urls)
        + "</urlset>\n", "utf-8")
    (ROOT / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {SITE_URL}sitemap.xml\n", "utf-8")
    print(f"Статических страниц: {total} (e/), sitemap.xml: {len(urls)} адресов")
