# Генераторы в JavaScript

Генераторы в JavaScript — это функции, которые могут **приостанавливать** выполнение и **возобновлять** его позже. Они обозначаются с помощью звёздочки (`function*`) и используют ключевое слово `yield` для приостановки выполнения.

---

### 📌 Синтаксис

```js
function* generatorFunction() {
  yield 1;
  yield 2;
  yield 3;
}
```

Вызов такой функции **не выполняет** её, а возвращает **объект генератора**:

```js
const gen = generatorFunction();
```

У объекта генератора есть метод `.next()`, который **возобновляет** выполнение до следующего `yield`.

---

### 🔄 Пример

```js
function* gen() {
  console.log('Start');
  yield 'A';
  console.log('Between');
  yield 'B';
  console.log('End');
}

const iterator = gen();

console.log(iterator.next()); // Start → { value: 'A', done: false }
console.log(iterator.next()); // Between → { value: 'B', done: false }
console.log(iterator.next()); // End → { value: undefined, done: true }
```

---

### 🧠 Что делает `yield`

* Приостанавливает выполнение функции
* Возвращает значение
* При следующем `next()` выполнение продолжается **после** `yield`

---

### 📥 Передача значения внутрь генератора

```js
function* gen() {
  const x = yield 'First';
  console.log('x:', x);
  const y = yield 'Second';
  console.log('y:', y);
}

const it = gen();
console.log(it.next());       // { value: 'First', done: false }
console.log(it.next(10));     // x: 10, { value: 'Second', done: false }
console.log(it.next(20));     // y: 20, { value: undefined, done: true }
```

---

### ✅ Использование

* Асинхронные потоки (`co`, `redux-saga`)
* Итераторы и ленивые вычисления
* Последовательная генерация данных

---

### Перебор генератора


Tаблица со всеми основными методами перебора генератора в JS:

| Метод             | Пример                            | Описание                                                         | Возвращает               | Требует `done`? |
| ----------------- | --------------------------------- | ---------------------------------------------------------------- | ------------------------ | --------------- |
| `.next()` вручную | `gen.next()`                      | Возвращает следующий элемент (объект с `value` и `done`)         | `{ value, done }`        | Да              |
| `for...of`        | `for (const v of gen()) {}`       | Перебирает генератор до `done === true`                          | Каждый `value`           | Да              |
| `...` (спред)     | `[...gen()]`                      | Расширяет генератор в массив                                     | `Array` из значений      | Да              |
| `Array.from()`    | `Array.from(gen())`               | Создаёт массив из значений генератора                            | `Array` из значений      | Да              |
| Деструктуризация  | `const [a, b] = gen();`           | Получает значения по порядку                                     | Переменные               | Да              |
| `for await...of`  | `for await (const v of gen()) {}` | Используется с **асинхронными генераторами** (`async function*`) | Каждый `value` (Promise) | Да              |

---

💡 **Примечание:**

* Методы работают **только один раз** с одним экземпляром генератора.
* `for await...of` требует `async function*` и используется для асинхронных потоков данных.


---

### 1. **Метод `.next()` вручную**

Это базовый способ:

```js
function* gen() {
  yield 'A';
  yield 'B';
  yield 'C';
}

const iterator = gen();

console.log(iterator.next()); // { value: 'A', done: false }
console.log(iterator.next()); // { value: 'B', done: false }
console.log(iterator.next()); // { value: 'C', done: false }
console.log(iterator.next()); // { value: undefined, done: true }
```

---

### 2. **Цикл `for...of`**

Автоматически вызывает `.next()` до тех пор, пока `done !== true`:

```js
for (const value of gen()) {
  console.log(value); // A, B, C
}
```

> ❗️ Примечание: `for...of` работает **только для конечных** генераторов.

---

### 3. **Оператор расширения (`...`)**

Позволяет получить все значения сразу:

```js
const values = [...gen()];
console.log(values); // ['A', 'B', 'C']
```

---

### 4. **`Array.from()`**

То же, что и оператор `...`, но чуть гибче (можно применить функцию к элементам):

```js
const arr = Array.from(gen());
console.log(arr); // ['A', 'B', 'C']
```

---

### 5. **Деструктуризация (редко)**

```js
const [a, b, c] = gen();
console.log(a, b, c); // 'A' 'B' 'C'
```

---

### 🔄 Повторный перебор

Генератор **одноразовый** — после завершения (`done: true`) его нельзя "сбросить". Нужно создать новый экземпляр:

```js
const g = gen();
[...g];        // OK
[...g];        // Пусто! Нужно снова вызвать `gen()`
```



