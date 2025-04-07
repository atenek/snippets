# AT_dagster-etl-tutorial

```bash 
 mkdir dagster-etl-tutorial  
 cd dagster-etl-tutorial

 pip install dagster dagster-webserver pandas dagster-duckdb

 dagster project from-example --example getting_started_etl_tutorial
```

```text
/AT_dagster-etl-tutorial$ tree -a  
.  
├── AT_dagster-etl-tutorial.md    
└── getting_started_etl_tutorial    
    ├── data  
    │   ├── products.csv  
    │   ├── sales_data.csv  
    │   ├── sales_reps.csv  
    │   └── sample_request  
    │       └── request.json  
    ├── etl_tutorial  
    │   └── definitions.py  
    ├── pyproject.toml  
    ├── py.typed  
    ├── setup.cfg  
    └── setup.py
```  
