[proproprogs -> js string](https://proproprogs.ru/javascript/metody-i-svoystva-strok)

В JavaScript строки (тип `string`) — это примитивный тип данных, представляющий последовательность символов. Они неизменяемы: любые операции над строками возвращают новую строку, не изменяя исходную.

### Создание строк

```js
let str1 = "Привет";
let str2 = 'Мир';
let str3 = `Привет, ${str2}`; // Интерполяция
```

### Основные свойства и методы строк

#### 🔹 Длина строки

```js
let s = "Hello";
console.log(s.length); // 5
```

#### 🔹 Доступ к символам

```js
console.log(s[1]);      // 'e'
console.log(s.charAt(1)); // 'e'
```

---

### 🔧 Методы работы со строками

#### 🔹 Поиск

* `indexOf(substr)` — индекс первого вхождения, либо `-1`
* `lastIndexOf(substr)` — последнее вхождение
* `includes(substr)` — `true`, если содержит подстроку
* `startsWith(substr)` / `endsWith(substr)` — начало / конец строки

```js
"Hello".includes("el"); // true
"Hello".startsWith("He"); // true
```

---

#### 🔹 Извлечение подстрок

* `slice(start, end)` — с `start` до `end` (не включая)
* `substring(start, end)` — как `slice`, но отрицательные индексы заменяются на 0
* `substr(start, length)` — устаревший, но всё ещё работает

```js
"abcdef".slice(1, 4); // "bcd"
```

---

#### 🔹 Изменение регистра

```js
"abc".toUpperCase(); // "ABC"
"XYZ".toLowerCase(); // "xyz"
```

---

#### 🔹 Замена

```js
"Яблоко".replace("бл", "р"); // "Яроко"
"1-2-3".replaceAll("-", ":"); // "1:2:3"
```

---

#### 🔹 Разделение и объединение

* `split(delimiter)` — разбивает строку в массив
* `join(delimiter)` — соединяет массив строк

```js
"а,б,в".split(","); // ["а", "б", "в"]
["а", "б", "в"].join("-"); // "а-б-в"
```

---

#### 🔹 Удаление пробелов

```js
"  текст  ".trim();     // "текст"
"  текст  ".trimStart(); // "текст  "
"  текст  ".trimEnd();   // "  текст"
```

---

#### 🔹 Повторение и сравнение

```js
"abc".repeat(3); // "abcabcabc"
"abc" === "abc"; // true
```

---

### Unicode и кодировки

JavaScript использует UTF-16. Символы за пределами BMP (например, эмодзи) занимают 2 "позиции":

```js
"😀".length === 2; // true
```

Для корректной работы с такими символами используют `Array.from(str)` или `for...of`.

---


Вот таблица с наиболее часто используемыми методами работы со строками в JavaScript:

| Категория     | Метод                    | Описание                                               |
| ------------- | ------------------------ | ------------------------------------------------------ |
| 📏 Длина      | `length`                 | Свойство для получения количества символов             |
| 📍 Поиск      | `indexOf`                | Первый индекс подстроки или -1                         |
|               | `lastIndexOf`            | Последний индекс подстроки или -1                      |
|               | `includes`               | Проверяет наличие подстроки                            |
|               | `startsWith`             | Проверяет, начинается ли строка с подстроки            |
|               | `endsWith`               | Проверяет, заканчивается ли строка подстрокой          |
| ✂️ Извлечение | `slice`                  | Возвращает подстроку                                   |
|               | `substring`              | Как `slice`, но отрицательные индексы → 0              |
|               | `substr` (устарел)       | Подстрока по индексу и длине                           |
| 🔠 Регистр    | `toUpperCase`            | Переводит в верхний регистр                            |
|               | `toLowerCase`            | Переводит в нижний регистр                             |
| 🧼 Пробелы    | `trim`                   | Удаляет пробелы по краям                               |
|               | `trimStart` / `trimEnd`  | Удаляет пробелы с начала / конца строки                |
| 🔁 Замена     | `replace`                | Заменяет подстроку                                     |
|               | `replaceAll`             | Заменяет все вхождения подстроки                       |
| 🔡 Разделение | `split`                  | Делит строку по разделителю                            |
|               | `join` (на массиве)      | Объединяет элементы массива в строку                   |
| 🔁 Повторение | `repeat`                 | Повторяет строку заданное количество раз               |
| 🔣 Получение  | `charAt` / `charCodeAt`  | Получение символа и его кода                           |
|               | `codePointAt`            | Поддержка символов за пределами BMP (например, эмодзи) |
| 🔁 Сравнение  | `localeCompare`          | Сравнивает строки с учётом локали                      |
| 🚶 Перебор    | `for...of`, `Array.from` | Перебор по символам (учитывает surrogate pairs)        |

---

Теперь давай подробнее по каждой группе с примерами:

### 📏 Длина строки

```js
let str = "Привет";
console.log(str.length); // 6
```

---

### 📍 Поиск

```js
let str = "Hello world";

str.indexOf("o");       // 4
str.lastIndexOf("o");   // 7
str.includes("world");  // true
str.startsWith("Hell"); // true
str.endsWith("ld");     // true
```

---

### ✂️ Извлечение

```js
let str = "JavaScript";

str.slice(4, 10);        // "Script"
str.substring(4, 10);    // "Script"
str.substr(4, 6);        // "Script" (устарел)
```

---

### 🔠 Изменение регистра

```js
"abc".toUpperCase(); // "ABC"
"XYZ".toLowerCase(); // "xyz"
```

---

### 🧼 Удаление пробелов

```js
"  текст  ".trim();      // "текст"
"  текст  ".trimStart(); // "текст  "
"  текст  ".trimEnd();   // "  текст"
```

---

### 🔁 Замена

```js
"Яблоко".replace("бл", "р");      // "Яроко"
"1-2-3".replaceAll("-", ":");     // "1:2:3"
```

---

### 🔡 Разделение и объединение

```js
"а,б,в".split(",");               // ["а", "б", "в"]
["а", "б", "в"].join("-");        // "а-б-в"
```

---

### 🔁 Повторение

```js
"abc".repeat(3); // "abcabcabc"
```

---

### 🔣 Получение символов

```js
let s = "Привет";

s.charAt(1);       // 'р'
s.charCodeAt(1);   // 1088
s.codePointAt(0);  // 1055 (для emoji и других спецсимволов)
```

---

### 🚶 Перебор символов (без ошибок на surrogate-пары)

```js
for (let ch of "👍🏽!") {
  console.log(ch);
}
// 👍
// 🏽
// !
```

Хорошо! Ниже — **шпаргалка по строкам в JavaScript на одном листе** (в компактном формате), а затем — **5 интерактивных задач** с растущей сложностью.

---

## 📄 ШПАРГАЛКА: Работа со строками в JavaScript

```
let str = "Привет, мир";

// 📏 Длина строки
str.length                 // 11

// 📍 Поиск
str.indexOf("мир")         // 8
str.includes("Привет")     // true
str.startsWith("При")      // true
str.endsWith("р")          // true

// ✂️ Извлечение
str.slice(8)               // "мир"
str.substring(8, 11)       // "мир"
str.substr(8, 3)           // "мир" (устаревшее)

// 🔠 Регистр
str.toUpperCase()          // "ПРИВЕТ, МИР"
str.toLowerCase()          // "привет, мир"

// 🔁 Замена
str.replace("мир", "друг") // "Привет, друг"
str.replaceAll("и", "!")   // "Пр!вет, м!р"

// 🔡 Разделение и объединение
str.split(", ")            // ["Привет", "мир"]
["а", "б", "в"].join("-")  // "а-б-в"

// 🧼 Удаление пробелов
"  test  ".trim()          // "test"
"  test  ".trimStart()     // "test  "
"  test  ".trimEnd()       // "  test"

// 🔁 Повторение
"ab".repeat(3)             // "ababab"

// 🔣 Получение символов
str[0]                     // "П"
str.charAt(1)              // "р"

// 🚶 Юникод + перебор
Array.from("😊a").length   // 2
[...new Set("аабв")]       // ["а", "б", "в"]
```

---

## 🎯 5 задач по строкам

### ✅ Задача 1: Разворот строки

```js
function reverse(str) {
  return str.split('').reverse().join('');
}

reverse("abc"); // "cba"
```

---

### ✅ Задача 2: Проверка палиндрома

```js
function isPalindrome(str) {
  let clean = str.toLowerCase().replace(/[^a-zа-я0-9]/gi, '');
  return clean === clean.split('').reverse().join('');
}

isPalindrome("А роза упала на лапу Азора"); // true
```

---

### ✅ Задача 3: Подсчет количества слов

```js
function countWords(str) {
  return str.trim().split(/\s+/).length;
}

countWords("  Hello   world  again "); // 3
```

---

### ✅ Задача 4: Частота символов

```js
function charFrequency(str) {
  let freq = {};
  for (let ch of str) {
    freq[ch] = (freq[ch] || 0) + 1;
  }
  return freq;
}

charFrequency("aabbcc"); // { a: 2, b: 2, c: 2 }
```

---

### ✅ Задача 5: Удалить дубликаты символов

```js
function removeDuplicates(str) {
  return Array.from(new Set(str)).join('');
}

removeDuplicates("aabbcc"); // "abc"
```

---








