// Разделы вики. Категории, перечисленные здесь, показываются всегда;
// категории, найденные парсером, добавляются из файлов data/<id>.js.
window.BR_CONFIG = {
  sections: [
    {
      id: "equipment",
      title: "Экипировка",
      icon: "🛡",
      source: "https://anteikutaern.at.ua/dropdir/",
      categories: []
    },
    {
      id: "pets",
      title: "Питомцы",
      icon: "🐾",
      source: "https://anteikutaern.at.ua/pety/",
      categories: []
    },
    {
      id: "mobs",
      title: "Противники",
      icon: "💀",
      source: "https://anteikutaern.at.ua/mobs/mobs/",
      categories: [
        { id: "normal", name: "Обычные" },
        { id: "elite", name: "Элита" },
        { id: "bosses", name: "Боссы" },
        { id: "champions", name: "Чемпионы" }
      ]
    },
    {
      id: "items",
      title: "Предметы",
      icon: "🎒",
      source: "https://anteikutaern.at.ua/items/",
      categories: []
    },
    {
      id: "npc",
      title: "НПС",
      icon: "🧙",
      source: "https://anteikutaern.at.ua/others/npc/",
      categories: []
    },
    {
      id: "skills",
      title: "Навыки",
      icon: "✨",
      source: "https://anteikutaern.at.ua/",
      categories: []
    },
    {
      id: "guides",
      title: "Статьи",
      icon: "📖",
      categories: []
    }
  ]
};
