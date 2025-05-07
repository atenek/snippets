# Object

```javascript
const obj = { a: 1, b: 2, c: 3 };

for (const key in obj) { console.log(key, obj[key]) };                                // Выводит ключ и значение

for (const key in obj) { if (obj.hasOwnProperty(key))  console.log(key, obj[key]); }  // Выводит ключ и значение не унаследованные!

Object.keys(obj).forEach(key => {  console.log(key, obj[key]); });                    // Ключ и значение

Object.values(obj).forEach(value => {  console.log(value); });                        // Только значения (1, 2, 3)

// Через forEach
Object.entries(obj).forEach(([key, value]) => { console.log(key, value); });          // a 1, b 2, c 3

// Через for...of с Object.entries 
for (const [key, value] of Object.entries(obj)) { console.log(key, value); }           // a 1, b 2, c 3 
```