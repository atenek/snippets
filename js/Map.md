# Map

`Map` — это структура данных, содержащая пары `ключ → значение`. В отличие от обычного объекта (`{}`), `Map`:
* сохраняет порядок добавления;
* может использовать в качестве ключей любые типы (в том числе объекты и функции);
* предоставляет более мощный API для перебора.

```javascript
let m = new Map();
 
m.set("string", "строка");
m.set(7, "простое число");
m.set(true, {descr: "boolean", value: true});
 
console.log( m.get("string") );
console.log( m.get(7) );
console.log( m.get(true) );
```


```new Map()``` – создаёт коллекцию;
```map.set(key, value)``` – записывает по ключу key значение value;  
```map.get(key)``` – возвращает значение по ключу или undefined, если ключ key отсутствует;  
```map.has(key)``` – возвращает true, если ключ key присутствует в коллекции, иначе false;  
```map.delete(key)``` – удаляет элемент по ключу key;  
```map.clear()``` – очищает коллекцию от всех элементов;  
```map.size```– возвращает текущее количество элементов.  


### Объекты в качестве ключей! 

```javascript
let user = {
    name: "JavaScript",
    type: "ES6"
};
 
let m = new Map();
m.set(user, "объект user");
console.log( m.get(user) );
```


### Создать объект Map на основе двумерного массива:
```javascript
let car = new Map([
         ["model", "opel"],
         ["color", 0xff],
         ["price", 1000]
    ]);
```

### Метод Object.fromEntries, из двумерного массива по формату ['ключ', значение] формирует объект:
```javascript
let prices = Object.fromEntries([
    ['banana', 1],
    ['orange', 2],
    ['meat', 4]
]);

let objLib = Object.fromEntries(lib.entries());
console.log(objLib);    
```




## 🔁 Основные способы перебора `Map`

| Перебор           | Использовать когда                              |
| ----------------- | ----------------------------------------------- |
| `map.forEach()`   | Простой перебор без преобразований              |
| `for...of`        | Гибкость, поддержка `break/continue`            |
| `map.entries()`   | Перебор ключей и значений (по умолчанию)        |
| `map.keys()`      | Только ключи                                    |
| `map.values()`    | Только значения                                 |
| `Array.from(map)` | Чтобы применять `map`, `filter`, `reduce` и др. |


### 1. **`map.forEach()`**

```js
let car = new Map([["model", "opel"], ["color", 0xff], ["price", 1000] ]);

car.forEach((value, key, map) => {
    console.log( `car[${key}] = ${value}` );
});
```
* Порядок — тот же, в каком были добавлены элементы.
* Аргументы: `value`, `key`, `map` (третий аргумент редко нужен).
* Третий аргумент `map` это сам объект Map, на котором вызывается forEach() (тот же самый)
  Иногда он бывает полезен:
    - для ссылок на оригинальную коллекцию, если ты перебираешь вложенные структуры;  
    - для передачи в замыкание без дополнительной переменной;
    - для генерации новых структур из исходной, зная контекст.

---

### 2. **`for...of` с `map.entries()`**

```js
for (const [key, value] of map.entries()) {
  console.log(`${key} = ${value}`);
}

// Короткая запись:
for (const [key, value] of map) {
  console.log(`${key} = ${value}`);
}
```
---

### 3. **`for...of` с `map.keys()` и `map.values()`**

```js
for (const key of car.keys()) {    //  только ключи из коллекции car
  console.log(key);
}

for (const value of car.values()) {  // значения
  console.log(value);
}
```

---

### 4. **Деструктуризация + Spread**
Полезно, если применять методы массивов к `Map`.

```js
const map = new Map([['x', 10], ['y', 20] ]);

const entries = [...map];          // [['x', 10], ['y', 20]]
const keys = [...map.keys()];      // ['x', 'y']
const values = [...map.values()];  // [10, 20]
```
---


## 🧠 Методы высшего порядка через преобразование `Map` в массив

`Map` сам по себе **не поддерживает методы `map()`, `filter()`, `reduce()` и т.д.**, нужно сначала превратить его в массив:

```js
const map = new Map([
  ['a', 1],
  ['b', 2],
  ['c', 3]
]);
```

### Пример: `map` + `map()`

```js
const mapped = [...map].map(([key, val]) => [key, val * 10]);
const newMap = new Map(mapped);
console.log(newMap); // Map { 'a' => 10, 'b' => 20, 'c' => 30 }
```

---

### Пример: `filter`

```js
const filtered = [...map].filter(([key, val]) => val > 1);
const newMap = new Map(filtered);
console.log(newMap); // Map { 'b' => 2, 'c' => 3 }
```

---

### Пример: `reduce`

```js
const sum = [...map].reduce((acc, [key, val]) => acc + val, 0);
console.log(sum); // 6
```

---

### Пример: `Object.fromEntries()` для перехода от `Map` к объекту

```js
const obj = Object.fromEntries(map);
console.log(obj); // { a: 1, b: 2, c: 3 }
```

---

## 🔄 Обратное преобразование: `Object.entries` → `Map`

```js
const obj = { a: 1, b: 2 };
const map = new Map(Object.entries(obj));
```
---