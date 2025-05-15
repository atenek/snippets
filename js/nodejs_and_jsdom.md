Чтобы писать код, предназначенный **и для браузера, и для Node.js с JSDOM**, нужно организовать проект так, чтобы:

* **основная логика** была независима от окружения;
* **точки входа** для браузера и Node.js были раздельны;
* **взаимодействие с DOM** (если есть) было абстрагировано.

Вот рекомендуемая структура проекта:

```
my-project/
├── src/
│   ├── core/
│   │   └── logic.js          # Независимая бизнес-логика
│   ├── browser/
│   │   └── index.js          # Точка входа для браузера
│   ├── node/
│   │   └── index.js          # Точка входа для Node.js + jsdom
│   └── dom/
│       └── dom-api.js        # Обёртка над DOM (querySelector и т.п.)
├── public/
│   └── index.html            # HTML-шаблон для браузера
├── package.json
└── jsdom-runner.js           # Альтернатива index.html для запуска через Node.js
```

### 1. `src/core/logic.js` // Независимая бизнес-логика

```js
export function runApp(domAPI) {
  const el = domAPI.getElement("#my-button");
  el.addEventListener("click", () => {
    domAPI.setText("#output", "Hello!");
  });
}
```

### 2. `src/dom/dom-api.js` // Обёртка над DOM (querySelector и т.п.)

```js
export function createDOMApi(document) {
  return {
    getElement: selector => document.querySelector(selector),
    setText: (selector, text) => {
      const el = document.querySelector(selector);
      if (el) el.textContent = text;
    }
  };
}
```

### 3. `src/browser/index.js`  // Точка входа для браузера

```js
import { runApp } from "../core/logic.js";
import { createDOMApi } from "../dom/dom-api.js";

document.addEventListener("DOMContentLoaded", () => {
  runApp(createDOMApi(document));
});
```

### 4. `src/node/index.js`  // Точка входа для Node.js + jsdom

```js
import { JSDOM } from "jsdom";
import { runApp } from "../core/logic.js";
import { createDOMApi } from "../dom/dom-api.js";
import fs from "fs";

const html = fs.readFileSync("public/index.html", "utf-8");
const dom = new JSDOM(html, { runScripts: "outside-only", resources: "usable" });

dom.window.addEventListener("load", () => {
  runApp(createDOMApi(dom.window.document));
});
```

### 5. `public/index.html`

```html
<!DOCTYPE html>
<html>
<head><title>Test</title></head>
<body>
  <button id="my-button">Click</button>
  <div id="output"></div>
  <script type="module" src="/src/browser/index.js"></script>
</body>
</html>
```

### 6. `jsdom-runner.js` (для запуска в Node)

```js
import "./src/node/index.js";
```

### Преимущества такой структуры:

* Ядро (`logic.js`) не зависит от среды;
* Можно тестировать в JSDOM, не дублируя код;
* Можно подключать логику к любому DOM — хоть JSDOM, хоть браузерному.

--- 
+ WS
---

Хорошо, вот обновлённая структура проекта с **учётом различий между `WebSocket` в браузере и `ws` в Node.js**, интегрированная в предложенную ранее архитектуру.

---



---

## 🔧 Код файлов

### jsdom-runner.js

```js
import "./src/node/index.js";
```

---

### public/index.html

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>App</title>
</head>
<body>
  <script type="module" src="/src/browser/index.js"></script>
</body>
</html>
```

---

### src/browser/index.js

```js
import { runApp } from "../shared/main.js";

const socket = new WebSocket("ws://localhost:8080");
runApp(socket, window);
```

---

### src/node/index.js

```js
import { readFileSync } from "fs";
import { JSDOM } from "jsdom";
import { runApp } from "../shared/main.js";

const html = readFileSync("public/index.html", "utf-8");

const dom = new JSDOM(html, {
  url: "http://localhost",
  runScripts: "dangerously",
  resources: "usable",
  pretendToBeVisual: true
});

const { window } = dom;

const wsModule = await import("ws");
const socket = new wsModule.default("ws://localhost:8080");

runApp(socket, window);
```

---

### src/shared/main.js

```js
export function runApp(socket, window) {
  socket.addEventListener("open", () => {
    console.log("[shared] WebSocket open");
    socket.send("Hello from shared code!");
  });

  socket.addEventListener("message", (event) => {
    console.log("[shared] Message:", event.data);
  });

  // Работа с DOM
  const div = window.document.createElement("div");
  div.textContent = "Приложение запущено!";
  window.document.body.appendChild(div);
}
```

---

## 📌 Преимущества структуры:

* **Разделение по средам** — `browser/` и `node/` специфичны.
* **Общая логика изолирована** в `shared/` и не зависит от среды.
* Ты явно создаёшь подходящий `WebSocket`-экземпляр в зависимости от среды.
* `runApp()` работает одинаково в обоих случаях — получая `socket` и `window`.

---


---

## 📌 Пояснение по структуре

### `public/`

Файлы, которые **не обрабатываются сборщиком** и просто копируются в `dist/`.
Используются напрямую как `http://localhost/index.html`, `logo.png`, и т.д.

### `src/`

Все исходные файлы:

* Разделение по средам (`browser`, `node`)
* Общая логика (`shared/`)
* Стили (`styles/`)
* UI/бизнес-компоненты (`components/`)

### `jsdom-runner.js`

Точка запуска, которая инициализирует jsdom и вызывает `src/node/index.js`.

### `server/`

Минимальный сервер для WebSocket/HTTP (если потребуется — например, для локального тестирования, моков, демонстраций).

### `tests/`

Для модульных и интеграционных тестов.

---

## 🔧 Пример использования

### ✅ В браузере:

* Загружается `index.html`
* Подключается `src/browser/index.js`
* Создаётся `WebSocket`, вызывается `runApp(socket, window)`

### ✅ В Node.js:

* Запускается `jsdom-runner.js`
* Загружается `index.html` в `JSDOM`
* Создаётся WebSocket через `ws`
* Вызывается `runApp(socket, window)`

---

## 🧩 Возможные расширения

| Функция                | Где добавить                                            |
| ---------------------- | ------------------------------------------------------- |
| Webpack/Vite           | Добавить `vite.config.js` или `webpack.config.js`       |
| SASS/LESS              | Использовать `*.scss` в `src/styles/`                   |
| Typescript             | Переименовать `.js` в `.ts` и настроить `tsconfig.json` |
| ESLint/Prettier        | `.eslintrc`, `.prettierrc`                              |
| CI/CD (GitHub Actions) | `.github/workflows/`                                    |
| Документация           | В `README.md` или `docs/`                               |

---


