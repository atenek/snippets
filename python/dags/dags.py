import numpy as np


def is_acyclic(adj_matrix):
    n = adj_matrix.shape[0]
    adj = adj_matrix.copy()
    in_deg = adj.sum(axis=0)
    visited = 0

    while True:
        zero_in = np.where(in_deg == 0)[0]
        if len(zero_in) == 0:
            break

        for v in zero_in:
            in_deg[v] = -1    # помечаем как удалённую
            in_deg -= adj[v]  # удаляем рёбра из V
            visited += 1

    return visited == n  # True если граф ацикличен



if __name__ == "__main__":
    # Пример 1: Aцикличный граф (0 → 1 → 2)
    adj1 = np.array([
        [0, 1, 0],
        [0, 0, 1],
        [0, 0, 0]
    ])
    print(is_acyclic(adj1))  # True

    # Пример 2: C циклом (0 → 1 → 2 → 0)
    adj2 = np.array([
        [0, 1, 0],
        [0, 0, 1],
        [1, 0, 0]
    ])
    print(is_acyclic(adj2))  # False
