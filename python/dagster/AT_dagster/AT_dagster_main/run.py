from dagster import materialize, DagsterInstance
from logic import iom
from logic.assets import Reader_0, Reader_1, Reader_2
from logic import defs
import time
from pathlib import Path
# execute_in_process()	Всегда исполняет всё заново как обычный Python
# Definitions.materialize()	Учитывает, что уже было материализовано (через IO Manager)


if __name__ == "__main__":

    if True:
        assets = [Reader_0, Reader_1, Reader_2]
        dag_instance = DagsterInstance.get()

        print("\n🔁 Первый запуск: Dagster выполнит все assets, начиная с Reader_2 -> Reader_1 -> Reader_0\n")
        result = materialize(assets, instance=dag_instance, resources={"my_io_manager": iom})


        assert result.success

        for i in ["2", "1", "0"]:
            print(f"\nРезультат Reader_{i}:\n", result.output_for_node(f"Reader_{i}"))

        print("\n---\n")
        time.sleep(5)

        print("\n🔁 Второй запуск: Dagster должен пропустить, если всё уже материализовано\n")
        # result2 = materialize(assets,  instance=dag_instance, resources={"my_io_manager": iom})
        result2 = materialize(assets, instance=dag_instance, resources={"my_io_manager": iom})
        assert result2.success

        for i in ["2", "1", "0"]:
            print(f"\nРезультат Reader_{i}:\n", result2.output_for_node(f"Reader_{i}"))






    else:
        job_def = defs.get_job_def("read_root")
        result = job_def.execute_in_process()
        assert result.success
        value = result.output_for_node("Reader_2")
        print("\nРезультат readfile2:\n", value)
        value = result.output_for_node("Reader_1")
        print("\nРезультат readfile1:\n", value)
        value = result.output_for_node("Reader_0")
        print("\nРезультат readfile0:\n", value)

        time.sleep(2)

        result = job_def.execute_in_process()
        assert result.success
        value = result.output_for_node("Reader_2")
        print("\nРезультат readfile2:\n", value)
        value = result.output_for_node("Reader_1")
        print("\nРезультат readfile1:\n", value)
        value = result.output_for_node("Reader_0")
        print("\nРезультат readfile0:\n", value)