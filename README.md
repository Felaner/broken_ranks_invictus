# Broken Ranks Wiki

Личная вики по игре Broken Ranks: экипировка, питомцы, противники, предметы, НПС, навыки.
Данные берутся с [anteikutaern.at.ua](https://anteikutaern.at.ua/).

## Просмотр

Открой `index.html` в браузере (двойным кликом — сервер не нужен).

- поиск по всей вики в шапке (горячая клавиша `/`), фильтр внутри раздела;
- категории разделов в боковом меню и чипах;
- вид «карточки» или «таблица» с сортировкой по любой характеристике;
- карточка записи справа: все характеристики, описание, списки (дроп и т.п.)
  со ссылками на связанные записи, `←`/`→` — соседние записи, `Esc` — закрыть;
- избранное (★) и тёмная тема сохраняются в браузере.

Иконки в блоках (дроп, навыки, команда…) кликабельны и ведут на соответствующую запись.

## Загрузка данных

Сайт-источник строит все страницы из одной базы `/raresImg/anteikuDB.json`,
поэтому данные берутся прямо из неё:

```bash
pip install -r scraper/requirements.txt
python -m playwright install firefox
python scraper/fetch_db.py --browser firefox            # база + иконки -> scraper/source, data/raresImg
python scraper/build.py                                 # база -> data/<раздел>.js
python scraper/fetch_db.py --browser firefox --needed   # докачать картинки, которых не хватает вики
```

`build.py` записывает в `scraper/source/needed_images.txt` картинки, на которые
ссылается вики, но которых ещё нет локально (модели питомцев/боссов и т.п.).
Старые `scrape.py` и `recon.py` оставлены для справки.

## Формат записи

```json
{
  "id": "mobs/bosses/...", "category": "bosses", "name": "...",
  "icon": "data/img/mobs/....png", "level": 25,
  "fields": [["Здоровье", "50000"], ["Аспект арены", "..."]],
  "blocks": [{"title": "Дроп", "html": "<img data-items=\"item27\" src=\"data/raresImg/...\">"}],
  "sourceUrl": "https://anteikutaern.at.ua/..."
}
```

Разделы и фиксированные категории (например, Обычные/Элита/Боссы/Чемпионы)
настраиваются в `assets/config.js`.
