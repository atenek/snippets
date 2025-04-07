from dagster import Definitions, AssetMaterialization, AssetCheckResult, mem_io_manager, InMemoryIOManager
from dagster._core.storage.fs_io_manager import fs_io_manager
from .assets import Reader_0, Reader_1, Reader_2, read_root
from typing import List
from pathlib import Path
import hashlib
import json

# from dagster import IOManager, io_manager
from dagster import Definitions, mem_io_manager # , memoized_io_manager

class MyCustomIOManager(InMemoryIOManager):
    def __init__(self, path_prefix):
        self.path_prefix = path_prefix
        self.path_prefix.mkdir(exist_ok=True)

    def _get_asset_path(self, asset_key):
        return self.path_prefix / f"{asset_key.path[-1]}.txt"

    def handle_output(self, context, obj):
        # context - метаданные (например, имя операции)
        # obj - данные, которые вернула операция
        print(f"MyCustomIOManager.handle_output: Запись в PersistStor {context.op_def.name} значение: {obj}")
        _path = self.path_prefix / f"{context.asset_key.path[-1]}.txt"
        data = str(obj)
        _path.write_text(data)
        data_hash = hashlib.md5(data.encode('utf-8')).hexdigest()

        context.log_event(
            AssetMaterialization(
                asset_key=context.asset_key,
                description=f"Persisted to {_path}",
                metadata={
                    "path": data,
                    "size": len(data.encode('utf-8')),
                    "hash": data_hash
                }
            )
        )


    def load_input(self, context):
       # context.log_event(AssetMaterialization(asset_key=context.asset_key))
        # Загружаем данные для следующей операции
       path = self.path_prefix / f"{context.upstream_output.asset_key.path[-1]}.txt"
       if not path.exists():
           raise ValueError(f"Data not found at {path}")
       return path.read_text()


iom = MyCustomIOManager(path_prefix=Path("./io0").resolve())

#defs = Definitions( assets = [Reader_0, Reader_1, Reader_2],
#                    jobs = [read_root],
#                    resources = {"my_io_manager": iom} )

defs = Definitions(
    assets=[Reader_0, Reader_1, Reader_2],
    resources={"io_manager": mem_io_manager.configured({"base_io_manager": MyCustomIOManager(Path("./io0").resolve())})}
)