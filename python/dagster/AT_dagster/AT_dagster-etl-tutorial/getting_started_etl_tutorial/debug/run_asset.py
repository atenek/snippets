import os

print(os.getcwd())
print(os.environ.get("PATH", "-None-"))

from etl_tutorial.definitions import duckdb, sales_data, sales_reps, products
from dagster import build_resources


if __name__ == "__main__":
    with build_resources({"duckdb": duckdb}) as resources:
        _sales_data = sales_data(resources.duckdb)
        _sales_reps = sales_reps(resources.duckdb)
        products(resources.duckdb)
