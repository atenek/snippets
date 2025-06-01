import math
import functools


def df_decorator(dx=0.0001):
    def func_decorator(func):
        @functools.wraps(func)
        def wrapper(x, *args, **kwargs):
            res = (func(x+dx, *args, **kwargs) - func(x, *args, **kwargs)) / dx
            return res
        return wrapper
    return func_decorator


@df_decorator(dx=0.01)
def sin_df(x):
    return math.sin(x)

# sin_df = df_decorator(dx=0.0001)(sin_df)

if __name__ == "__main__":
    x = sin_df(2)
    print(x)