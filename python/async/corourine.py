import inspect
import generator

async def Coro():
    return 10


coro = Coro()

print(inspect.iscoroutinefunction(Coro))    # True

print(type(Coro))  # <class 'function'>
print(dir(Coro))
# ['__annotations__', '__builtins__', '__call__', '__class__', '__closure__', '__code__', '__defaults__',
#  '__delattr__',  '__dict__', '__dir__', '__doc__', '__eq__', '__format__', '__ge__', '__get__', '__getattribute__',
#  '__getstate__', '__globals__', '__gt__', '__hash__', '__init__', '__init_subclass__', '__kwdefaults__', '__le__',
#  '__lt__', '__module__', '__name__', '__ne__', '__new__', '__qualname__', '__reduce__', '__reduce_ex__', '__repr__',
#  '__setattr__', '__sizeof__', '__str__', '__subclasshook__', '__type_params__']


print([x for x in dir(Coro) if x not in dir(generator.Gen)])    # => []
print([y for y in dir(generator.Gen) if y not in dir(Coro)])    # => []

print(Coro.__class__.__mro__) # (<class 'function'>, <class 'object'>)

print(inspect.iscoroutine(coro))      # True

print(type(coro))  # <class 'coroutine'>
print(dir(coro))
# ['__await__', '__class__', '__del__', '__delattr__', '__dir__', '__doc__', '__eq__', '__format__', '__ge__',
#  '__getattribute__', '__getstate__', '__gt__', '__hash__', '__init__', '__init_subclass__', '__le__', '__lt__',
#  '__name__', '__ne__', '__new__', '__qualname__', '__reduce__', '__reduce_ex__', '__repr__', '__setattr__',
#  '__sizeof__', '__str__', '__subclasshook__', 'close', 'cr_await', 'cr_code', 'cr_frame', 'cr_origin', 'cr_running',
#  'cr_suspended', 'send', 'throw']

print(coro.__class__.__mro__)  # (<class 'coroutine'>, <class 'object'> )

print([x for x in dir(coro) if x not in dir(generator.g)])
# => ['__await__', 'cr_await', 'cr_code', 'cr_frame', 'cr_origin', 'cr_running', 'cr_suspended']

print([y for y in dir(generator.g) if y not in dir(coro)])
# => ['__iter__', '__next__', 'gi_code', 'gi_frame', 'gi_running', 'gi_suspended', 'gi_yieldfrom']

coro.close()
exit()
