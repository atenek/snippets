# Array

```javascript
let ar = [ "Яблоко", "Слива" ];

arr.push("Груша");// Добавление в конец массива
arr.push(4);      // Добавление в конец массива

arr.pop();        // Удаление последнего элемента из массива
let delElem = ar.pop(); // pop возвращает удаленный элемент
console.log( delElem );

let fruits = ["Яблоко", "Апельсин", "Груша"];
let delElem = fruits.shift(); 
console.log( fruits );

fruits.shift();         // shift удаляет первый элемент массива:
arr.unshift('Персик');  // Добавляет 'Персик' в начало

arr[3] = "4";     // Добавляет(изменяет) "4" на 3 позицию 
```

### Многомерные массивы

```js
let matrix = [
  [1, 2, 3],
  [4, 5, 6],
  [7, 8, 9]
];
 
console.log( matrix );
```

# Перебор массива

### for цикл

```javascript
for(let i=0; i < matrix.length; i++) {
    let cols = "";
    for(let j = 0; j < matrix[i].length; j++)
       cols += matrix[i][j] + " ";
 
    console.log(cols); 
}
```

### for...of  
```js
for(let row of matrix) {
    let cols = "";
    for(let val of row)
       cols += val + " ";
 
    console.log(cols); 
}
```
### forEach

```js
const arr = [1, 2, 3];

arr.forEach((value, index) => {
  console.log(`Index: ${index}, Value: ${value}`);
});
```

## Методы высшего порядка


| Метод         | Что делает                                                       | Возвращает                  | Изменяет массив |
| ------------- | ---------------------------------------------------------------- | --------------------------- | --------------- |
| `map`         | Преобразует каждый элемент                                       | Новый массив                | ❌               |
| `filter`      | Оставляет только те элементы, которые прошли фильтр              | Новый массив                | ❌               |
| `reduce`      | Сводит массив к одному значению                                  | Любое значение              | ❌               |
| `reduceRight` | Как `reduce`, но справа налево                                   | Любое значение              | ❌               |
| `forEach`     | Просто выполняет функцию для каждого элемента                    | `undefined`                 | ❌               |
| `some`        | Проверяет, есть ли хотя бы один элемент, удовлетворяющий условию | `true` / `false`            | ❌               |
| `every`       | Проверяет, удовлетворяют ли все элементы                         | `true` / `false`            | ❌               |
| `find`        | Находит **первый** подходящий элемент                            | Элемент или `undefined`     | ❌               |
| `findIndex`   | Индекс первого подходящего элемента                              | Число или `-1`              | ❌               |
| `flatMap`     | Комбинирует `map` и `flat(1)`                                    | Новый массив                | ❌               |
| `flat`        | Разворачивает вложенные массивы                                  | Новый массив                | ❌               |
| `sort`        | Сортирует элементы                                               | **Ссылка на тот же массив** | ✅               |
| `reverse`     | Меняет порядок элементов на обратный                             | **Ссылка на тот же массив** | ✅               |


---

### `map` возвращает новый массив

```javascript
const arr = [1, 2, 3];
const doubled = arr.map(x => x * 2);
console.log(doubled); // [2, 4, 6]
```

### `filter` — фильтрация

```javascript
const arr = [1, 2, 3, 4];
const even = arr.filter(x => x % 2 === 0);
console.log(even); // [2, 4]
```

### `reduce` — аккумулирование
```javascript
const arr = [1, 2, 3, 4];
const sum = arr.reduce((acc, val) => acc + val, 0);
console.log(sum); // 10
```


### 🔁 `some` 
Проверяет, удовлетворяет ли **хотя бы один** элемент условию:
```js
const arr = [1, 2, 3];
const hasEven = arr.some(x => x % 2 === 0); // true
```


### ✅ `every`
Проверяет, удовлетворяют ли **все** элементы условию:
```js
const arr = [2, 4, 6];
const allEven = arr.every(x => x % 2 === 0); // true
```

### 🔍 `find`
Возвращает **первый элемент**, подходящий под условие, или `undefined`:
```js
const arr = [5, 8, 12];
const found = arr.find(x => x > 6); // 8
```

### 🔢 `findIndex`
Возвращает индекс первого элемента, удовлетворяющего условию, или `-1`:
```js
const arr = [10, 20, 30];
const idx = arr.findIndex(x => x === 20); // 1
```

### 📋 `flatMap`
Комбинирует `map` и `flat`. Применяет функцию и «сплющивает» результат на один уровень:
```js
const arr = [1, 2, 3];
const result = arr.flatMap(x => [x, x * 2]);
// [1, 2, 2, 4, 3, 6]
```

### 🔂 `flat`
Разворачивает вложенные массивы (один уровень по умолчанию):
```js
const nested = [1, [2, [3, 4]]];
console.log(nested.flat());       // [1, 2, [3, 4]]
console.log(nested.flat(2));      // [1, 2, 3, 4]
```

### 🔁 `reduceRight`
То же, что `reduce`, но идет **справа налево**:
```js
const arr = ['a', 'b', 'c'];
const res = arr.reduceRight((acc, val) => acc + val); // "cba"
```

### 🔄 `sort`
Сортировка элементов. Может принимать функцию сравнения:
> ⚠️ `sort` изменяет исходный массив.

```js
const arr = [3, 1, 2];
arr.sort((a, b) => a - b); // [1, 2, 3]
```

### 🔁 `reverse`
Переворачивает порядок элементов:
```js
const arr = [1, 2, 3];
arr.reverse(); // [3, 2, 1]
```


#### !!! for...in (не рекомендуется для массивов)
Этот цикл предназначен для объектов, а не массивов — он перебирает ключи (индексы), а не значения, и может включать прототипные свойства:

```js
const arr = [1, 2, 3];

for (const key in arr) {
  console.log(arr[key]);
}
```