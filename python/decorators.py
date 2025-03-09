from sys import _getframe as Getframe

#  Декоратор — это функция, которая принимает другую функцию и дополняет её поведение без изменения её кода.
#  В процессе декорирования используется три функции
#  Декорируемая функция <some_func> это та функция поведение которой будет дополнено декоратором. Это исходная функция.
#
#  Функция-декоратор <func_decorator>, принимает Декорируемую функцию <some_func> и возвращает Функцию-обёртку <wrapper>.
#  Функция-декоратор это функция принимающая в качестве аргумента исходную функция и возвращающая Функцию-обёртку.
#  Она служит для замены Декорируемуой функции на Функцию-обёртку.
#  Имя Функции-декоратора это имя декоратора.
#  Имя Функции-декоратора используется со знаком @ для декорирования: @func_decorator.
#
#  Функция-обёртка <wrapper> это та функция которая будет фактически выполнется после декорирования.
#  То есть внешне вызов декорированной функции выгляит как вызов  исходной функции  some_func()
#  а фактически вызывется wrapper(). Имя Функции-обёртки скрыто в Функции-декораторе
#  Функция-обёртка <wrapper> принимает аргументы которые может модифицировав предать в исходную функция
#  Функция-обёртка <wrapper> возвращает результат который может быть получен на основе результата исходную функция
#  Функция-обёртка <wrapper> в крайнем случае вообще может не использовать исходную функцию.


# ===== without args (1-level decorator) =====

def func_decorator(func):
    print("Hi")
    def wrapper():
        print(f"------ {Getframe().f_code.co_name}: before func() ------")
        rezult = func()
        print(f"------ {Getframe().f_code.co_name}: after func()  ------")
        return rezult
    return wrapper


def some_l1_func1():
    print(f"{Getframe().f_code.co_name}: BODY")


@func_decorator
def some_l1_func2():
    print(f"{Getframe().f_code.co_name}: BODY")

print("line 1")
# func_decorator(some_l1_func1)()
some_l1_func2()

exit()
# -------------------------

@func_decorator
def some_func2():
    print(f"{Getframe().f_code.co_name}: BODY")


some_func2()

# =========================

# ==== with func args and return =====

def func_decorator_args(func):
    def wrapper(*args, **kwargs):
        print(f"------ {Getframe().f_code.co_name}: before func({args} {kwargs}) ------")
        rezult = func(*args, **kwargs)
        print(f"------ {Getframe().f_code.co_name}: after func({args} {kwargs}) ------")
        return rezult

    return wrapper

@func_decorator_args
def some_func3(a, b, c=None):
    rezult = f"rezult a:{a}; b:{b}; c:{c}; "
    print(f"{Getframe().f_code.co_name}: BODY. {rezult}")
    return rezult


print(f"REZULT: {some_func3(10, 20, 300)}")

# =========================


