# Corutine

Corutine это объект обладающий следующими свойствами:
- [awaitable объект](./awaitable-object.md) реализующий методы 
  - ```__await__()``` возвращает генератор (отсюда следствие Все корутины (coroutine) — это awaitable);
  - ```send(value)```
  - ```throw(exc_type, ...)```
  - ```close()```
- дополнительно реализующий методы 
  - ```cr_await``` Если корутина ждёт другую корутину (например, await other_coro()), то здесь будет объект, который сейчас ожидается. 
    Если корутина не находится в await, то None.
  - ```cr_code```	Объект code (байткод) функции, из которой создана корутина. Аналогично func.__code__.
  - ```cr_frame```	Объект frame, содержащий стек вызова на текущий момент выполнения корутины. None, если корутина завершена.
  - ```cr_origin```	Кортеж (файл, строка, функция), где была создана корутина.
  - ```cr_running```	True, если корутина уже выполняется в данный момент (например, если внутри await другой корутины).
  - ```cr_suspended```	True, если корутина была приостановлена (например, после await).

Корутины поддерживают множество точек входа, выхода и возобновления их выполнения.

Класс который является корутиной
```python
class MyCoroutine:
    def __init__(self):
        self.gen = self._run()  # Генератор как основа корутины

    def _run(self):
        print("Start coroutine execution")
        result = yield  # Ожидаем `send()`
        print(f"Received: {result}")
        yield  # Еще одно ожидание
        print("End coroutine execution")

    def __await__(self):
        return self.gen  # `await` передает управление генератору

    def send(self, value):
        return self.gen.send(value)  # Поддержка `send()`

    def throw(self, ex_type, ex_value=None, ex_traceback=None):
        return self.gen.throw(ex_type, ex_value, ex_traceback)  # Поддержка `throw()`

    def close(self):
        return self.gen.close()  # Поддержка `close()`

async def main():
    coro = MyCoroutine()
    await coro  # Запускаем корутину
```

### Создание корутины

- Синтаксис [```async def```](./async_def.md) который определет функцию конструктор корутины.  
  Функция определенная через [```async def```](./async_def.md) не является корутиной, но возвращает корутину которая представляет собой объект .
- Декоратор ```@types.coroutine``` делает обычный yield-генератор корутиной.

###  Запуск корутины