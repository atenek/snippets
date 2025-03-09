import sys
import inspect
import traceback

# sys._getframe() — это низкоуровневая функция в Python, которая позволяет получить объект текущего стека вызовов
# Функция sys._getframe() низкоуровневая и "внутренняя" (_ в имени).
# В некоторых средах с ограниченной безопасностью её использование может быть запрещено!

# sys._getframe(depth=0) depth — необязательный аргумент, сколько уровней вверх по стеку вызовов нужно подняться.
# (по умолчанию depth=0) — текущий фрейм.

# .f_code.co_name   — имя текущей функции.
# .f_globals        — глобальные переменные.
# .f_locals         — локальные переменные.
# .f_lineno         — текущая строка выполнения.
# .f_back           — ссылка на предыдущий фрейм (стек вызовов).

def func1():
    func2()


def func2():
    frame = sys._getframe()
    print(f"current frame: {frame.f_code.co_name}")  # func2
    caller_frame = sys._getframe(1)
    print(f"caller frame {caller_frame.f_code.co_name}")  # func1
    next_frame = sys._getframe(2)
    print(f"next frame {next_frame.f_code.co_name}")  # func1
    next2_frame = sys._getframe(2)
    print(f"next2 frame {next2_frame.f_code.co_name}")  # func1


func1()

# ====== inspect позволяет получить имя текущей функции с помощью inspect.currentframe():

def func3():
    frame = inspect.currentframe()
    print(f"func3 current frame: {frame.f_code.co_name}")  # func2


func3()


# =====  traceback

def my_function():
    stack = traceback.extract_stack()
    print(stack)


my_function()
