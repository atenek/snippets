import ast
import networkx as nx
import astpretty
import pprint
import inspect

class DependencyVisitor(ast.NodeVisitor):
    def __init__(self):
        self.graph = nx.DiGraph()
        self.current_function = None

    def visit_Module(self, node):
        print(f"visit_Module {node} {node.body}")
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        print(f"visit_FunctionDef {node}")
        self.current_function = node.name
        self.graph.add_node(node.name, type='function')
        self.generic_visit(node)
        self.current_function = None

    def visit_Assign(self, node):
        print(f"visit_Assign {node}")
        targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
        deps = set()

        # ищем зависимости в правой части выражения
        for child in ast.walk(node.value):
            if isinstance(child, ast.Name):
                deps.add(child.id)
            elif isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                deps.add(child.func.id)

        for var in targets:
            self.graph.add_node(var, type='variable')
            for dep in deps:
                self.graph.add_edge(dep, var)
            if self.current_function:
                self.graph.add_edge(var, self.current_function)

        self.generic_visit(node)

    def visit_Call(self, node):
        print(f"visit_Call {node}")
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if self.current_function:
                self.graph.add_edge(func_name, self.current_function)
        self.generic_visit(node)


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


def f(x: int):
    return 2 * x

def test_func(a: int, b: int) -> int:
    '''

    :param a: a-comment
    :param b: b-comment
    :return:
    '''
    c: int = a + b
    d = f(c)
    return d


if __name__ == "__main__":
    source_code = inspect.getsource(test_func)
    tree = ast.parse(source_code)

    # print("===== print tree =====")
    # print(ast.dump(tree, indent=4))
    # print("====================")

    print("==== pprint tree ====")
    astpretty.pprint(tree)
    print("=====================")

    # print("==== json tree ====")
    # pprint.pprint(ast_to_dict(tree))
    # print("=====================")

    visitor = DependencyVisitor()
    visitor.visit(tree)
    G = visitor.graph

    for edge in G.edges:
        print(f"{edge[0]} -> {edge[1]}")
