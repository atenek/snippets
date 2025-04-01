import inspect
import asyncio
import pprint

async def foo():
    pass

coro = foo()
print(inspect.isawaitable(coro))  #  (корутина) => True
print(inspect.iscoroutinefunction(foo))

pprint.pprint(foo)        # <function foo at 0x762a327da340>
pprint.pprint(dir(coro))  #  '__await__', '__getstate__', 'close',  'cr_await',  'cr_code',  'cr_frame',  'cr_origin',  'cr_running',  'cr_suspended',  'send',  'throw'
coro.close()


class MyAwaitable:
    def __await__(self):
        yield from asyncio.sleep(1).__await__()
        return "Кастомный результат"


async def main():
    obj = MyAwaitable()
    result = await obj  # Ожидание 1 секунду
    print(result)       # "Кастомный результат"

asyncio.run(main())
