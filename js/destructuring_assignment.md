# Деструктурирующее присваивание

```javascript
let cars = ["yaguar", "porshe", "mercedes"];
let [car1, car2, car3] = cars;

let [car1, , car2] = ["yaguar", "porshe", "mercedes"];
```

```javascript
let [firstName, middleName, lastName] = "Иван Иванович Иванов".split(" ");
console.log(firstName, middleName, lastName);
```

```javascript
let [fr1, fr2, ...last] = ["Груша", "Слива", "Яблоко", "Персик", "Виноград"];
console.log(fr1, fr2, last);
```

```javascript
let [fr1, fr2, ...last] = ["Груша", "Слива", "Яблоко", "Персик", "Виноград"];
console.log(fr1, fr2, last);
```

```javascript
let [a1, a2, a3, a4] = "Иван"; 
console.log(a1, a2, a3, a4);
// каждой переменной присваивается отдельный символ строки.
```

```javascript
let [one, two, three] = new Set([1, 2, 3]);
console.log(one, two, three);
```
