from datetime import datetime as DT

if __name__ == '__main__':
    dt_now = DT.now()
    time_stamp = f"{dt_now.strftime('%Y-%m-%d_%H-%M-%S_')}{f'{dt_now.microsecond}'[:3]:03}"
    print(time_stamp)