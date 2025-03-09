
def f_closure(s):
    def g():
        print(s)
    return g


if __name__ == "__main__":
    f = f_closure("lexus")
    f()
