
### 📘 **1. Официальная документация модуля `ast`**

**Ссылка**: [https://docs.python.org/3/library/ast.html](https://docs.python.org/3/library/ast.html)

Это основной источник, где:

* Описаны узлы AST (`Module`, `Expr`, `FunctionDef`, `Assign`, и т. д.)
* Показано, как использовать `ast.parse`, `ast.walk`, `ast.NodeVisitor`, `ast.NodeTransformer`
* Дано описание структуры узлов (какие поля у `FunctionDef` и т. д.)

---

### 📘 **2. Спецификация AST Python**

**Ссылка (на исходный `.rst` файл CPython)**:
[https://github.com/python/cpython/blob/main/Parser/Python.asdl](https://github.com/python/cpython/blob/main/Parser/Python.asdl)

Файл `Python.asdl` (Abstract Syntax Description Language) определяет структуру AST в CPython. Он описывает:

* Все типы узлов
* Их поля
* Иерархию

---

### 🧰 **3. Исходники CPython (в частности, модуль `_ast`)**

**Ссылка**: [https://github.com/python/cpython/tree/main/Python](https://github.com/python/cpython/tree/main/Python)

Внутри CPython, Python AST сначала создаётся как parse tree (Concrete Syntax Tree), затем преобразуется в AST, а потом — в байт-код.

Файл `Python/ast.c` — логика преобразования из CST в AST.

---

### 📌 **4. Интерактивное исследование AST**

Если хочешь исследовать AST вручную:

```python
import ast
tree = ast.parse("def foo(x): return x + 1")
print(ast.dump(tree, indent=4))  # С Python 3.9+
```

---

### 📚 Дополнительно:

* **PEP 339**: описывает структуру стандартного компилятора CPython.
* **PEP 484** (аннотации типов), **PEP 563** и др. — иногда затрагивают AST, если расширяют синтаксис языка.
* **`typed_ast`** — альтернативная реализация AST, поддерживающая старые версии Python.

