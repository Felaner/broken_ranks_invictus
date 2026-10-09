// Демо-данные: показываются, только пока парсер не создал настоящие файлы data/<раздел>.js.
// Все записи вымышленные и нужны лишь для проверки интерфейса.
(function () {
  const D = (window.BR_DATA = window.BR_DATA || {});
  const demo = (n, extra) => Object.assign({ description: "Демо-запись. Настоящие данные появятся после запуска парсера." }, extra, { name: "Демо: " + n });

  D.equipment = {
    categories: [{ id: "helmets", name: "Шлемы" }, { id: "weapons", name: "Оружие" }, { id: "armor", name: "Броня" }],
    entries: [
      demo("шлем", { category: "helmets", level: 5, fields: [["Уровень", "5"], ["Защита", "12"], ["Прочность", "40"]] }),
      demo("шлем II", { category: "helmets", level: 12, fields: [["Уровень", "12"], ["Защита", "27"], ["Прочность", "60"]] }),
      demo("меч", { category: "weapons", level: 8, fields: [["Уровень", "8"], ["Урон", "14-20"], ["Сила", "+3"]] }),
      demo("доспех", { category: "armor", level: 10, fields: [["Уровень", "10"], ["Защита", "35"]] }),
    ],
  };
  D.pets = { entries: [demo("питомец", { category: "_", fields: [["Бонус", "+5% опыта"]] })] };
  D.mobs = {
    entries: [
      demo("противник", { category: "normal", level: 3, fields: [["Уровень", "3"], ["Здоровье", "120"]],
        lists: [{ title: "Добыча", items: ["Демо: шлем", "Демо: меч"] }] }),
      demo("элитный противник", { category: "elite", level: 15, fields: [["Уровень", "15"], ["Здоровье", "2400"]] }),
      demo("босс", { category: "bosses", level: 25, fields: [["Уровень", "25"], ["Здоровье", "50000"]] }),
      demo("чемпион", { category: "champions", level: 20, fields: [["Уровень", "20"], ["Здоровье", "9000"]] }),
    ],
  };
  D.items = { categories: [{ id: "potions", name: "Зелья" }], entries: [demo("зелье", { category: "potions", fields: [["Эффект", "+100 HP"]] })] };
  D.npc = { entries: [demo("НПС", { category: "_", fields: [["Локация", "Демо-город"]] })] };
})();
