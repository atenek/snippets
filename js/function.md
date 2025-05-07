#  Function

```javascript
// Function Declaration (объявление функции)
function out_log() {
    console.log("Вызов функции");

function sum(a, b) {
         return a+b;
}

// Function Expression (функциональное выражение)
function showMsg() {
         console.log("Hello!");
}

let showMsg = function() {
         console.log("Hello!");
};

// Стрелочные функции
let anonym = () => console.log("это cтрелочная функция");

let anonym = () => 48+30;  
// если нет фигурных скобок, подразумевается оператор return 

let anonym = () => { 48+30 };  
// если тело в фигурных скобках, оператор return не работет по умолчанию и его следет прописывать явно 

let anonym = () => { return 48+30 };  

//Остаточные аргументы только при объявлении функции !!!
function sumAll(arg1, arg2, ...args) { // args это массив
    console.log("Hello!", arg1, arg2);
    let sum = 0;
    for(let val of args)
         sum += val;
    return sum;
}


// оператор расширения итерируемых объектов (при вызове функций, в массивах и во всех остальных случаях )
let items = [1, 2, 3, 4, 5];
let max0 = Math.max(items[0], items[1], ..., items[4]);
let max1 = Math.max(...items);
let max = Math.max(...items, 1000, ...digs, 0);
let comp = [...items, -1, -2, -3, ...digs];

}
