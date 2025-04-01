import inspect


def Gen():
    while True:
        yield 100


g = Gen()

print(inspect.isgeneratorfunction(Gen))    # true

print(type(Gen))  # <class 'function'>
print(dir(Gen))   # generatorfunction
# ['__annotations__', '__builtins__', '__call__', '__class__', '__closure__', '__code__', '__defaults__', '__delattr__',
#  '__dict__', '__dir__', '__doc__', '__eq__', '__format__', '__ge__', '__get__', '__getattribute__', '__getstate__',
#  '__globals__', '__gt__', '__hash__', '__init__', '__init_subclass__', '__kwdefaults__', '__le__', '__lt__',
#  '__module__', '__name__', '__ne__', '__new__', '__qualname__', '__reduce__', '__reduce_ex__', '__repr__',
#  '__setattr__', '__sizeof__', '__str__', '__subclasshook__', '__type_params__']

print(inspect.isgenerator(g))              # true

print(type(g))  # <class 'generator'>
print(dir(g))   # generator
# [ '__class__', '__del__', '__delattr__', '__dir__', '__doc__', '__eq__', '__format__', '__ge__', '__getattribute__',
#   '__getstate__', '__gt__', '__hash__', '__init__', '__init_subclass__', '__iter__', '__le__', '__lt__', '__name__',
#   '__ne__', '__new__', '__next__', '__qualname__', '__reduce__', '__reduce_ex__', '__repr__', '__setattr__',
#   '__sizeof__', '__str__', '__subclasshook__', 'close', 'gi_code', 'gi_frame', 'gi_running', 'gi_suspended',
#   'gi_yieldfrom', 'send', 'throw' ]
print(g.__class__.__mro__)   # (<class 'generator'>, <class 'object'>)


