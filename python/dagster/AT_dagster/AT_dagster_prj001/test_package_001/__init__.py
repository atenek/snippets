from dagster import Definitions
from .assets import company_id, company_details, store_to_db
from dagster._core.storage.fs_io_manager import fs_io_manager
from .jobs import my_sync_job


defs = Definitions(
    assets=[company_id, company_details, store_to_db],
    jobs=[my_sync_job],
    resources={"my_io_manager": fs_io_manager.configured({"base_dir": "/home/alex/Prj/2_dev/lbft/AT_dagster_prj001/io"})}
)
