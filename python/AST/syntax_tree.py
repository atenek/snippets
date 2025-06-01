import ast
import networkx as nx
import matplotlib.pyplot as plt
import astpretty
import pprint
import inspect
from typing import Dict

def f(x: int):
    return 2 * x

def test_func(a: int, b: int):
    c: int = a + b
    return f(c)


def ast_to_dict(node):
    if isinstance(node, ast.AST):
        result = {
            "type": type(node).__name__,
            "fields": {},
        }

        # Стандартные поля: lineno, col_offset и др.
        for attr in ('lineno', 'col_offset', 'end_lineno', 'end_col_offset'):
            if hasattr(node, attr):
                result[attr] = getattr(node, attr)

        # Рекурсивно сериализуем вложенные поля
        for field_name, value in ast.iter_fields(node):
            result["fields"][field_name] = ast_to_dict(value)

        return result
    elif isinstance(node, list):
        return [ast_to_dict(x) for x in node]
    else:
        return node  # literal (str, int, None и т.п.)

if __name__ == "__main__":
    source_code = inspect.getsource(test_func)
    tree = ast.parse(source_code)
    print("===== print tree =====")
    print(ast.dump(tree, indent=4))
    print("====================")

    print("==== pprint tree ====")
    astpretty.pprint(tree)
    print("=====================")

    print("==== json tree ====")
    pprint.pprint(ast_to_dict(tree))
    print("=====================")


    dag = nx.DiGraph()


    class DependencyVisitor(ast.NodeVisitor):
        def __init__(self):
            self.current_target = None

        def visit_Assign(self, node):
            if isinstance(node.targets[0], ast.Name):
                self.current_target = node.targets[0].id
                dag.add_node(self.current_target)
                self.visit(node.value)
            self.current_target = None

        def visit_Name(self, node):
            if isinstance(node.ctx, ast.Load) and self.current_target:
                # Добавляем зависимость: current_target ← node.id
                dag.add_edge(node.id, self.current_target)

    # Запуск обхода
    visitor = DependencyVisitor()
    visitor.visit(tree)

    # Вывод графа
    print("Зависимости:")
    for u, v in dag.edges:
        print(f"{v} зависит от {u}")

    # (необязательно) Визуализация
    pos = nx.spring_layout(dag)
    nx.draw(dag, pos, with_labels=True, arrows=True, node_color='lightblue')
    plt.show()
