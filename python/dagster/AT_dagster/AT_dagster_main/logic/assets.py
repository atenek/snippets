from dagster import asset, get_dagster_logger, job, define_asset_job, AssetSelection, FreshnessPolicy
from pathlib import Path
from datetime import datetime as dt

logger = get_dagster_logger()

@asset(io_manager_key="my_io_manager",
       freshness_policy=FreshnessPolicy(maximum_lag_minutes=60),
       compute_kind="file_io", metadata={"cacheable": True} )
def Reader_2(context) -> str:
    path = Path("./datafiles/file2.txt")
    rez = f"read from source file '{path}': value: '{path.read_text()}' at {dt.now()}"
    logger.info(f"asset:Reader_2: read from source file '{path}': value: '{rez}'")
    print(f"asset:Reader_2: read from source file '{path}': value: '{rez}'")
    return str({"name": "Reader_2", "input": "", "file2": rez, "time": str(dt.now())})

@asset(io_manager_key="my_io_manager",
       freshness_policy=FreshnessPolicy(maximum_lag_minutes=60),
       compute_kind="file_io", metadata={"cacheable": True} )
def Reader_1(context, Reader_2: str) -> str:
    path = Path("./datafiles/file1.txt")
    rez = f"read from source file '{path}': value: '{path.read_text()}' at {dt.now()}"
    logger.info(f"asset:Reader_1: read from source file '{path}': value: '{rez}'")
    print(f"asset:Reader_1: read from source file '{path}': value: '{rez}'")
    return str({"name": "Reader_1", "input": Reader_2, "file1": rez, "time": str(dt.now())})

@asset(io_manager_key="my_io_manager",
       freshness_policy=FreshnessPolicy(maximum_lag_minutes=60),
       compute_kind="file_io", metadata={"cacheable": True} )
def Reader_0(context, Reader_1: str) -> str:
    path = Path("./datafiles/file0.txt")
    rez = f"read from source file '{path}': value: '{path.read_text()}' at {dt.now()}"
    logger.info(f"asset:Reader_0: read from source file '{path}': value: '{rez}'")
    print(f"asset:Reader_0: read from source file '{path}': value: '{rez}'")
    return str({"name": "Reader_0", "input": Reader_1, "file0": rez, "time": str(dt.now())})

read_root = define_asset_job(
    name="read_root",
    selection=AssetSelection.assets("Reader_0", "Reader_1", "Reader_2")
)

# @job
# def my_job():
#     result2 = readfile2()  # Сохраняем результат выполнения readfile2
#     result1 = readfile1(readfile2=result2)  # Передаем результат readfile2 в readfile1
#     readfile0(readfile1=result1)  # Передаем результат readfile1 в readfile0

