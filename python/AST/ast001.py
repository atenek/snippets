import ast

# Исходный код
code = """
# type: --ignoreAlex--
def func001(x):
    x = x + 10
    x = x * x
    print(x)
    return x
    x = 200


"""


class MyVisitor(ast.NodeVisitor):

    def generic_visit(self, node):
        print(f"Узел: {type(node).__name__}")
        super().generic_visit(node)  # Важно: вызываем родительский метод!

    def visit_Name(self, node):
        print(f"  Переменная: {node.id}")
        super().generic_visit(node)  # Продолжаем обход method, self.generic_visit)

if __name__ == "__main__":
    # Парсинг кода в AST
    tree = ast.parse(code)
    print("="*40)
    print(ast.dump(tree, indent=4))
    print("="*40)
    visitor = MyVisitor()
    visitor.visit(tree)

    node_types = [
        cls.__name__ for cls in ast.__dict__.values()
        if isinstance(cls, type) and issubclass(cls, ast.AST)
    ]
    print(f"node_types {node_types}")

