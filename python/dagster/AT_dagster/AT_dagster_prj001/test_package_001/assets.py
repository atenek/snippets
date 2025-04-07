from dagster import asset, get_dagster_logger
import requests


@asset(io_manager_key="my_io_manager")
def company_id() -> int:
    logger = get_dagster_logger()
    response = requests.get("https://dummyjson.com/users/1")
    logger.info(f"HTTP Response: {response.status_code}, {response.json()}")
    return response.json()["id"]


@asset(io_manager_key="my_io_manager")
def company_details(company_id: int) -> dict:
    response = requests.get(f"https://dummyjson.com/users/{company_id}")
    return {
        "name": response.json()["firstName"],
        "email": response.json()["email"],
    }


@asset(io_manager_key="my_io_manager")
def store_to_db(company_details: dict):
    print(f"Сохраняем в БД: {company_details}")
