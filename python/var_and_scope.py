def outer():
    def inner():
        # global x
        # nonlocal x
        print(f"inner before dir :{dir()}")          # dir()       Cписок всех доступных имен (переменных и функций)
        print(f"inner before globals :{globals()}")  # globals()   Словарь всех глобальных переменных
        print(f"inner before locals :{locals()}")    # locals()    Словарь всех локальных переменных
        x = 'inner_value_x'
        print(f"inner after dir :{dir()}")          # dir()       Cписок всех доступных имен (переменных и функций)
        print(f"inner after globals :{globals()}")  # globals()   Словарь всех глобальных переменных
        print(f"inner after locals :{locals()}")    # locals()    Словарь всех локальных переменных
        print()

    global x
    x = 'outer_value_x'
    print(f"outer before dir :{dir()}")          # dir()       Cписок всех доступных имен (переменных и функций)
    print(f"outer before globals :{globals()}")  # globals()   Словарь всех глобальных переменных
    print(f"outer before locals :{locals()}")    # locals()    Словарь всех локальных переменных
    print()
    inner()
    print(f"outer after dir :{dir()}")          # dir()       Cписок всех доступных имен (переменных и функций)
    print(f"outer after globals :{globals()}")  # globals()   Словарь всех глобальных переменных
    print(f"outer after locals :{locals()}")    # locals()    Словарь всех локальных переменных
    print()


if __name__ == "__main__":
    x = 'global_value_x'
    print(f"global before dir :{dir()}")          # dir()       Cписок всех доступных имен (переменных и функций)
    print(f"global before globals :{globals()}")  # globals()   Словарь всех глобальных переменных
    print(f"global before locals :{locals()}")    # locals()    Словарь всех локальных переменных
    print()

    outer()

    print(f"global after dir :{dir()}")           # dir()       Cписок всех доступных имен (переменных и функций)
    print(f"global after globals :{globals()}")   # globals()   Словарь всех глобальных переменных
    print(f"global after locals :{locals()}")     # locals()    Словарь всех локальных переменных
    print()
