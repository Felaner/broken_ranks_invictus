// Разделы вики. Категории, перечисленные здесь, показываются всегда;
// категории, найденные парсером, добавляются из файлов data/<id>.js.
window.BR_CONFIG = {
  sections: [
    {
      id: "equipment",
      title: "Экипировка",
      icon: "🛡",
      categories: []
    },
    {
      id: "pets",
      title: "Питомцы",
      icon: "🐾",
      categories: []
    },
    {
      id: "mobs",
      title: "Противники",
      icon: "💀",
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
      categories: []
    },
    {
      id: "npc",
      title: "НПС",
      icon: "🧙",
      categories: []
    },
    {
      id: "skills",
      title: "Навыки",
      icon: "✨",
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
