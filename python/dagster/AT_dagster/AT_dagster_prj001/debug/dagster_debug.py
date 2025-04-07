import os
print(os.getcwd())
os.chdir("..")
print(os.getcwd())
from test_package_001 import company_id, company_details, store_to_db
from test_package_001 import my_sync_job
from dagster import job, op, AssetSelection

@op
def get_company_id():
    return company_id()

@op
def get_company_details(company_id):
    return company_details(company_id)

@op
def store_data_to_db(company_details):
    return store_to_db(company_details)

@job
def my_sync_job():
    company_id = get_company_id()
    company_details = get_company_details(company_id)
    store_data_to_db(company_details)



if __name__ == "__main__":
    job_mode = True
    if job_mode:
        result = my_sync_job.execute_in_process()
        assert result.success
    else:
        _company_id = company_id()
        _company_details = company_details(_company_id)
        store_to_db = store_to_db(_company_details)
