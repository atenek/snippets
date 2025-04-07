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

#defs = Definitions( assets = [Reader_0, Reader_1, Reader_2],
#                    jobs = [read_root],
#                    resources = {"my_io_manager": iom} )

defs = Definitions(
    assets=[Reader_0, Reader_1, Reader_2],
    resources={"io_manager": mem_io_manager.configured({"base_io_manager": MyCustomIOManager(Path("./io0").resolve())})}
)