import pandas as pd
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import os

if __name__ == "__main__":
    matplotlib.use('Qt5Agg')
    fig, ax1 = plt.subplots()
    max_t = 0x1000
    t_arg = np.array(range(0, max_t))
    f1 = np.sin(0.002 * t_arg)
    f1 += np.random.normal(0.002, 0.008, size=f1.shape)

    f2 = np.cos(0.0035 * t_arg)
    f2 += np.random.normal(0.002, 0.008, size=f1.shape)

    ax1.plot(t_arg, f1, label='ps', color='green')
    ax1.set_xlabel('t')
    ax1.set_ylabel('ps', color='green')
    ax1.tick_params(axis='y', labelcolor='green')

    ax2 = ax1.twinx()

    ax1.plot(t_arg, f2, label='ps', color='blue')
    ax2.set_ylabel('sin', color='blue')
    ax2.tick_params(axis='y', labelcolor='blue')

    ax3 = ax1.twinx()
    dt = 0x0F0
    rez = []
    for i in range(0, max_t):
        if i < dt:
            rez.append(None)
        else:
            rez.append(20000*np.cov(f1[i-dt:i], f2[i-dt:i])[0, 1]/dt)

    f3 = np.array(rez)
    ax1.plot(t_arg, f3, label='ps', color='red')

    ax3.set_ylabel('cos', color='red')
    ax3.tick_params(axis='y', labelcolor='red')

    fig.tight_layout()  # Чтобы графики не перекрывались




    t_arg, Y = np.meshgrid(t_arg, Y)
    Z = np.sin(np.sqrt(t_arg ** 2 + Y ** 2))  # Функция для поверхности

    # Создание 3D-фигуры
    fig = plt.figure(figsize=(8, 6))
    ax = fig.add_subplot(111, projection='3d')

    # Построение поверхности
    ax.plot_surface(X, Y, Z, cmap='viridis')

    # Показ графика
    plt.show()