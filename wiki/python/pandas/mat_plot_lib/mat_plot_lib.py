import pandas as pd
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
import os

if __name__ == "__main__":
    matplotlib.use('Qt5Agg')
    fig, ax1 = plt.subplots()
    x_arr1 = np.array(range(0, 300))
    f_arr1 = np.array(range(-100, 200))
    f_arr2 = np.array(range(-200, 100))

    ax1.plot(x_arr1, f_arr1, label='ps', color='green')
    ax1.set_xlabel('time')
    ax1.set_ylabel('ps', color='green')
    ax1.tick_params(axis='y', labelcolor='green')

    ax2 = ax1.twinx()

    ax1.plot(x_arr1, f_arr2, label='ps', color='green')
    ax2.set_ylabel('vol', color='blue')
    ax2.tick_params(axis='y', labelcolor='blue')

    fig.tight_layout()  # Чтобы графики не перекрывались
    plt.show()