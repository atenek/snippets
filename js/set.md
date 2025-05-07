# Set

## 📦 Что такое `Set`

`Set` — это коллекция **уникальных значений**, без ключей. Основные особенности:

* Хранит **только значения** (без пар ключ → значение);
* Исключает дубликаты;
* Сохраняет порядок добавления;
* Поддерживает перебор.

```new Set(iterable)``` – создаёт Set, если в качестве аргумента был предоставлен итерируемый объект (обычно это массив), то копирует его значения в Set;  
```set.add(value)``` – добавляет значение (если оно уже есть, то ничего не происходит), возвращает тот же объект set;   
```set.delete(value)``` – удаляет значение, возвращает true если value было найдено и удалено, иначе false;   
```set.has(value)``` – возвращает true, если значение присутствует в коллекции, иначе false;   
```set.clear()``` – удаляет все значения из набора;   
```set.size``` – возвращает количество элементов в наборе.  

```js
let guests = new Set();
 
let alex = { name: "Alexey", old: 25 };
let oleg = { name: "Oleg", old: 32 };
let masha = { name: "Masha", old: 18 };
 
guests.add(alex);
guests.add(oleg);
guests.add(masha);
guests.add(alex);
guests.add(masha);

const other_set = new Set([1, 2, 3, 2]);

```

| Перебор           | Что делает                       | Возвращает  | Изменяет Set |
| ----------------- | -------------------------------- | ----------- | ------------ |
| `forEach()`       | Обходит значения                 | `undefined` | ❌            |
| `for...of`        | Универсальный способ             | `value`     | ❌            |
| `values()`        | Итератор значений                | `Iterator`  | ❌            |
| `keys()`          | То же, что `values()`            | `Iterator`  | ❌            |
| `entries()`       | Пары `[value, value]`            | `Iterator`  | ❌            |
| `Array.from(set)` | Преобразование в массив          | Массив      | ❌            |
| `new Set([...])`  | Создание нового `Set` из массива | `Set`       | ❌            |

## 🔁 Основные способы перебора `Set`

### 1. **`set.forEach()`**

```js
set.forEach((value) => {
  console.log(value);
});
```

> Примечание: у `Set.forEach()` оба аргумента (`value`, `key`) будут одинаковыми, чтобы API был совместим с `Map`.

```js
set.forEach((value, key) => {
  console.log(key === value); // true
});
```

---

### 2. **`for...of`**

```js
for (const value of set) {
  console.log(value);
}
```

---

### 3. **`set.values()` / `set.keys()` / `set.entries()`**

* `set.values()` — возвращает итератор по значениям.
* `set.keys()` — возвращает то же самое (для совместимости с `Map`).
* `set.entries()` — возвращает пары `[value, value]`.

```js
for (const val of set.values()) console.log(val);
for (const key of set.keys()) console.log(key);       // то же самое
for (const [a, b] of set.entries()) console.log(a, b); // value, value
```

---

## 🧠 Методы высшего порядка (через массив)

Как и `Map`, `Set` **не имеет встроенных `map()`, `filter()` и т.д.**, но ты можешь использовать их через `Array.from()` или spread:

```js
const set = new Set([1, 2, 3, 4]);
```

---

### Пример: `map()`

```js
const doubled = new Set([...set].map(x => x * 2));
console.log(doubled); // Set { 2, 4, 6, 8 }
```

---

### Пример: `filter()`
```js
const filtered = new Set([...set].filter(x => x % 2 === 0));
console.log(filtered); // Set { 2, 4 }
```

---

### Пример: `reduce()`
```js
const sum = [...set].reduce((acc, val) => acc + val, 0);
console.log(sum); // 10
```

---

## 🔁 Преобразование `Set` ↔ `Array`
```js
const arr = Array.from(set);      // [1, 2, 3]
const set2 = new Set(arr);        // Set { 1, 2, 3 }

const unique = new Set([1, 2, 2, 3]); // Удаление дубликатов из массива
```
---
