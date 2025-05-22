
* прячет системный курсор;
* отображает "фейковый курсор" (`div`);
* имитирует перемещение курсора к элементу;
* выполняет действия: клик, двойной клик, ввод текста, установка чекбокса и т. д.

---

## ✅ Основной код (можно вставить в `<script>` или отдельный `ui_tester.js`)

```js
(() => {
  // === Фейковый курсор ===
  const cursor = document.createElement("div");
  Object.assign(cursor.style, {
    position: "fixed",
    width: "14px",
    height: "14px",
    background: "black",
    borderRadius: "50%",
    zIndex: 99999,
    pointerEvents: "none",
    left: "0px",
    top: "0px",
    transition: "left 0.05s linear, top 0.05s linear"
  });
  document.body.appendChild(cursor);
  document.body.style.cursor = "none";

  let posX = 0, posY = 0;

  async function moveCursorTo(elem, duration = 500) {
    const rect = elem.getBoundingClientRect();
    const targetX = rect.left + rect.width / 2;
    const targetY = rect.top + rect.height / 2;

    const steps = Math.max(10, duration / 16);
    const dx = (targetX - posX) / steps;
    const dy = (targetY - posY) / steps;

    for (let i = 0; i < steps; i++) {
      posX += dx;
      posY += dy;
      cursor.style.left = `${posX}px`;
      cursor.style.top = `${posY}px`;
      await new Promise(r => setTimeout(r, 16));
    }

    posX = targetX;
    posY = targetY;
    cursor.style.left = `${posX}px`;
    cursor.style.top = `${posY}px`;
  }

  function triggerEvent(elem, type, options = {}) {
    const evt = new MouseEvent(type, {
      bubbles: true,
      cancelable: true,
      view: window,
      clientX: posX,
      clientY: posY,
      ...options
    });
    elem.dispatchEvent(evt);
  }

  // === Действия ===
  const actions = {
    async click(selector) {
      const elem = document.querySelector(selector);
      if (!elem) throw `click: элемент ${selector} не найден`;
      await moveCursorTo(elem);
      triggerEvent(elem, "mousedown");
      triggerEvent(elem, "mouseup");
      triggerEvent(elem, "click");
    },

    async doubleClick(selector) {
      const elem = document.querySelector(selector);
      if (!elem) throw `doubleClick: элемент ${selector} не найден`;
      await moveCursorTo(elem);
      triggerEvent(elem, "mousedown");
      triggerEvent(elem, "mouseup");
      triggerEvent(elem, "click");
      await new Promise(r => setTimeout(r, 100));
      triggerEvent(elem, "mousedown");
      triggerEvent(elem, "mouseup");
      triggerEvent(elem, "click");
      triggerEvent(elem, "dblclick");
    },

    async inputText(selector, text) {
      const elem = document.querySelector(selector);
      if (!elem || !(elem instanceof HTMLInputElement || elem instanceof HTMLTextAreaElement))
        throw `inputText: элемент ${selector} не является текстовым полем`;
      await moveCursorTo(elem);
      elem.focus();
      elem.value = text;
      elem.dispatchEvent(new Event("input", { bubbles: true }));
      elem.dispatchEvent(new Event("change", { bubbles: true }));
    },

    async check(selector, state = true) {
      const elem = document.querySelector(selector);
      if (!elem || elem.type !== "checkbox")
        throw `check: элемент ${selector} не является checkbox`;
      await moveCursorTo(elem);
      elem.checked = state;
      elem.dispatchEvent(new Event("change", { bubbles: true }));
    }
  };

  // === Глобальный объект ===
  window.UIAutoTest = {
    ...actions,
    moveCursorTo
  };
})();
```

---

## ✅ Пример использования

Вставь в HTML ниже `<script src="...ui_tester.js"></script>`, либо прямо после этого кода:

```html
<script>
  window.addEventListener("DOMContentLoaded", async () => {
    await UIAutoTest.click("#startBtn");
    await UIAutoTest.inputText("#username", "admin");
    await UIAutoTest.check("#agree", true);
    await UIAutoTest.doubleClick("#submitBtn");
  });
</script>
```

---

## 📌 Что реализовано:

| Метод                         | Описание                   |
| ----------------------------- | -------------------------- |
| `click(selector)`             | Одиночный клик             |
| `doubleClick(selector)`       | Двойной клик               |
| `inputText(selector, text)`   | Ввод текста                |
| `check(selector, true/false)` | Чекбокс установка          |
| `moveCursorTo(elem)`          | Движение фейкового курсора |

---

# Анимация

Чтобы добавить анимацию движения и визуальное отображение кликов (с указанием кнопки 1-2-3), сделаем следующее:

---


1. **Плавное перемещение фейкового курсора** от текущей позиции к цели.
2. **Анимация клика**:

   * визуальное "сжатие/расширение" курсора;
   * отображение номера кнопки (1 — левая, 2 — средняя, 3 — правая).
3. **Работает для `click()` и `doubleClick()`**.

---

## 🧩 Обновлённый код

```js
(() => {
  const cursor = document.createElement("div");
  const clickMark = document.createElement("div");

  Object.assign(cursor.style, {
    position: "fixed",
    width: "16px",
    height: "16px",
    background: "black",
    borderRadius: "50%",
    zIndex: 99999,
    pointerEvents: "none",
    left: "0px",
    top: "0px",
    transform: "translate(-50%, -50%)",
    transition: "left 0.05s linear, top 0.05s linear"
  });

  Object.assign(clickMark.style, {
    position: "fixed",
    fontSize: "12px",
    color: "white",
    background: "red",
    padding: "1px 4px",
    borderRadius: "6px",
    zIndex: 99998,
    pointerEvents: "none",
    transform: "translate(-50%, -150%)",
    opacity: 0,
    transition: "opacity 0.3s ease"
  });

  document.body.appendChild(cursor);
  document.body.appendChild(clickMark);
  document.body.style.cursor = "none";

  let posX = 0, posY = 0;

  async function moveCursorTo(elem, duration = 500) {
    const rect = elem.getBoundingClientRect();
    const targetX = rect.left + rect.width / 2;
    const targetY = rect.top + rect.height / 2;

    const steps = Math.max(10, duration / 16);
    const dx = (targetX - posX) / steps;
    const dy = (targetY - posY) / steps;

    for (let i = 0; i < steps; i++) {
      posX += dx;
      posY += dy;
      cursor.style.left = `${posX}px`;
      cursor.style.top = `${posY}px`;
      await new Promise(r => setTimeout(r, 16));
    }

    posX = targetX;
    posY = targetY;
    cursor.style.left = `${posX}px`;
    cursor.style.top = `${posY}px`;
  }

  function triggerEvent(elem, type, button = 0) {
    const evt = new MouseEvent(type, {
      bubbles: true,
      cancelable: true,
      view: window,
      clientX: posX,
      clientY: posY,
      button: button
    });
    elem.dispatchEvent(evt);
  }

  async function animateClick(button = 0) {
    // "Сжатие" курсора
    cursor.style.transform = "translate(-50%, -50%) scale(0.6)";
    // Показать цифру на клик
    clickMark.textContent = String(button + 1);
    clickMark.style.left = `${posX}px`;
    clickMark.style.top = `${posY}px`;
    clickMark.style.opacity = "1";

    await new Promise(r => setTimeout(r, 200));

    cursor.style.transform = "translate(-50%, -50%) scale(1)";
    clickMark.style.opacity = "0";
  }

  const actions = {
    async click(selector, button = 0) {
      const elem = document.querySelector(selector);
      if (!elem) throw `click: элемент ${selector} не найден`;
      await moveCursorTo(elem);
      await animateClick(button);
      triggerEvent(elem, "mousedown", button);
      triggerEvent(elem, "mouseup", button);
      triggerEvent(elem, "click", button);
    },

    async doubleClick(selector, button = 0) {
      const elem = document.querySelector(selector);
      if (!elem) throw `doubleClick: элемент ${selector} не найден`;
      await moveCursorTo(elem);
      await animateClick(button);
      triggerEvent(elem, "mousedown", button);
      triggerEvent(elem, "mouseup", button);
      triggerEvent(elem, "click", button);

      await new Promise(r => setTimeout(r, 100));

      await animateClick(button);
      triggerEvent(elem, "mousedown", button);
      triggerEvent(elem, "mouseup", button);
      triggerEvent(elem, "click", button);
      triggerEvent(elem, "dblclick", button);
    },

    async inputText(selector, text) {
      const elem = document.querySelector(selector);
      if (!elem || !(elem instanceof HTMLInputElement || elem instanceof HTMLTextAreaElement))
        throw `inputText: элемент ${selector} не является текстовым полем`;
      await moveCursorTo(elem);
      elem.focus();
      elem.value = text;
      elem.dispatchEvent(new Event("input", { bubbles: true }));
      elem.dispatchEvent(new Event("change", { bubbles: true }));
    },

    async check(selector, state = true) {
      const elem = document.querySelector(selector);
      if (!elem || elem.type !== "checkbox")
        throw `check: элемент ${selector} не является checkbox`;
      await moveCursorTo(elem);
      elem.checked = state;
      elem.dispatchEvent(new Event("change", { bubbles: true }));
    }
  };

  window.UIAutoTest = {
    ...actions,
    moveCursorTo
  };
})();
```

---

## ✅ Использование

```js
await UIAutoTest.click("#btn1", 0); // Левая кнопка
await UIAutoTest.click("#btn2", 1); // Средняя
await UIAutoTest.click("#btn3", 2); // Правая
await UIAutoTest.doubleClick("#btn1", 0);
```

---

## 📌 Что делает

| Возможность              | Реализовано |
| ------------------------ | ----------- |
| Движение курсора         | ✅ плавно    |
| Сжатие курсора при клике | ✅           |
| Показ номера кнопки мыши | ✅           |
| Указание кнопки (0,1,2)  | ✅           |

---

**Анимация“волны”** при клике — расширяющийся и исчезающий круг, как ripple-эффект.

---

* При каждом клике в `animateClick()` создаётся временный `<div>`, стилизованный как круг.
* Он расширяется и исчезает за \~500 мс.
---

### 🧩 Обновить в существующем коде `animateClick()` — **вместо текущего**:

```js
async function animateClick(button = 0) {
  // "Сжатие" курсора
  cursor.style.transform = "translate(-50%, -50%) scale(0.6)";

  // Всплывающая цифра кнопки
  clickMark.textContent = String(button + 1);
  clickMark.style.left = `${posX}px`;
  clickMark.style.top = `${posY}px`;
  clickMark.style.opacity = "1";

  // Волна
  const ripple = document.createElement("div");
  Object.assign(ripple.style, {
    position: "fixed",
    left: `${posX}px`,
    top: `${posY}px`,
    width: "10px",
    height: "10px",
    background: "rgba(0, 0, 0, 0.2)",
    borderRadius: "50%",
    transform: "translate(-50%, -50%) scale(0)",
    zIndex: 99997,
    pointerEvents: "none",
    transition: "transform 0.5s ease-out, opacity 0.5s ease-out",
    opacity: "1"
  });
  document.body.appendChild(ripple);

  // Запуск анимации ripple
  requestAnimationFrame(() => {
    ripple.style.transform = "translate(-50%, -50%) scale(5)";
    ripple.style.opacity = "0";
  });

  // Удаление ripple через 500 мс
  setTimeout(() => ripple.remove(), 500);

  await new Promise(r => setTimeout(r, 200));

  cursor.style.transform = "translate(-50%, -50%) scale(1)";
  clickMark.style.opacity = "0";
}
```

---

### 🔎 Эффект

* Курсор сжимается.
* Показывается цифра кнопки (1-2-3).
* В месте клика появляется круг, который быстро расширяется и исчезает.




