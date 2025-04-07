from dagster import asset, get_dagster_logger, job, define_asset_job, AssetSelection
from pathlib import Path
from datetime import datetime as dt

@asset(io_manager_key="my_io_manager")
def readfile2(context) -> str:
    logger = get_dagster_logger()
    if context.has_run_storage:
        cached_data = context.resources.my_io_manager.load("my_asset_data")
        if cached_data:
            logger.info(f"readfile2: cached_data exist'")
            return cached_data
        else:
            logger.info(f"readfile2: cached_data NOT exist'")
            path = Path("datafiles/file2.txt")
            rez = f"{path.read_text()} {dt.now()}"
            logger.info(f"readfile2: read from file {path}: '{rez}'")
            print(f"readfile2: read from file {path}: '{rez}'")
    context.resources.my_io_manager.save("my_asset_data", rez)
    return rez

@asset(io_manager_key="my_io_manager")
def readfile1(context, readfile2: str) -> str:
    logger = get_dagster_logger()
    path = Path("datafiles/file1.txt")
    rez = f"{path.read_text()} {dt.now()}"
    logger.info(f"readfile1: read from file {path}: '{rez}'")
    print(f"readfile1: read from file {path}: '{rez}'")
    return f"{readfile2}\n{rez}"

@asset(io_manager_key="my_io_manager")
def readfile0(context, readfile1: str) -> str:
    logger = get_dagster_logger()
    path = Path("datafiles/file0.txt")
    rez = f"{path.read_text()} {dt.now()}"
    logger.info(f"readfile0: read from file {rez}: '{rez}'")
    print(f"readfile0: read from file {rez}: '{rez}'")
    return f"{readfile1}\n{rez}"

read_root = define_asset_job(
    name="read_root",
    selection=AssetSelection.assets("readfile0", "readfile1", "readfile2")
)

# @job
# def my_job():
#     result2 = readfile2()  # Сохраняем результат выполнения readfile2
#     result1 = readfile1(readfile2=result2)  # Передаем результат readfile2 в readfile1
#     readfile0(readfile1=result1)  # Передаем результат readfile1 в readfile0


