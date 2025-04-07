from dagster import Definitions
from dagster._core.storage.fs_io_manager import fs_io_manager
from .assets import readfile0, readfile1, readfile2, read_root


defs = Definitions(
    assets=[readfile0, readfile1, readfile2],
    jobs=[read_root],
    resources={"my_io_manager": fs_io_manager.configured({"base_dir": "/home/alex/Prj/2_dev/lbft/AT_dugster/AT_dagster_files/io"})}
)