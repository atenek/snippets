
📦 Структура проекта

```text
AT_dagster_prj/   
├── dagster_project/  
│   ├── __init__.py  
│   ├── assets.py         ← здесь описаны зависимости и логика  
│   └── jobs.py           ← объединение asset'ов в pipeline  
├── workspace.yaml  
├── dagster.yaml  
└── pyproject.toml  
```

### prj001_byGuide  
$  
$ pip install dagster dagster-webserver pandas  
$  
$  
$ cd ./AT_dagster_prj  
$ dagster dev --log-level=debug  
$  



