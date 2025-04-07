from dagster import materialize, resource
from logic import defs
from logic.assets import readfile0, readfile1, readfile2
from dagster._core.storage.fs_io_manager import fs_io_manager
import time
# execute_in_process()	Всегда исполняет всё заново как обычный Python
# Definitions.materialize()	Учитывает, что уже было материализовано (через IO Manager)

if __name__ == "__main__":

    if True:
        assets = [readfile0, readfile1, readfile2]

        print("\n🔁 Первый запуск: Dagster выполнит все assets, начиная с readfile0\n")
        result = materialize(
            assets,
            #selection=["readfile0", "readfile1", "readfile2"],
            resources={
                "my_io_manager": fs_io_manager.configured({
                "base_dir": "/home/alex/Prj/2_dev/lbft/AT_dugster/AT_dagster_files/io"})})
        assert result.success

        value = result.output_for_node("readfile2")
        print("\nРезультат readfile2:\n", value)
        value = result.output_for_node("readfile1")
        print("\nРезультат readfile1:\n", value)
        value = result.output_for_node("readfile0")
        print("\nРезультат readfile0:\n", value)

        print("\n---\n")
        time.sleep(2)

        print("\n🔁 Второй запуск: Dagster должен пропустить, если всё уже материализовано\n")
        result2 = materialize(
            assets,
            #selection=["readfile0", "readfile1", "readfile2"],
            resources={
                "my_io_manager": fs_io_manager.configured({
                    "base_dir": "/home/alex/Prj/2_dev/lbft/AT_dugster/AT_dagster_files/io"})})
        assert result2.success

        value = result2.output_for_node("readfile2")
        print("\nРезультат readfile2:\n", value)
        value = result2.output_for_node("readfile1")
        print("\nРезультат readfile1:\n", value)
        value = result2.output_for_node("readfile0")
        print("\nРезультат readfile0:\n", value)

    else:
        job_def = defs.get_job_def("read_root")
        result = job_def.execute_in_process()
        assert result.success
        value = result.output_for_node("readfile2")
        print("\nРезультат readfile2:\n", value)
        value = result.output_for_node("readfile1")
        print("\nРезультат readfile1:\n", value)
        value = result.output_for_node("readfile0")
        print("\nРезультат readfile0:\n", value)

        time.sleep(2)

        result = job_def.execute_in_process()
        assert result.success
        value = result.output_for_node("readfile2")
        print("\nРезультат readfile2:\n", value)
        value = result.output_for_node("readfile1")
        print("\nРезультат readfile1:\n", value)
        value = result.output_for_node("readfile0")
        print("\nРезультат readfile0:\n", value)
