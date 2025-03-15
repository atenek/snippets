# Тип данных в Pandas Dataframe

###  При открытии файла
```dtype={"col_name": type}``` Словарь (dict of type) который задает тип данных для столбцов.  
Работает быстрее, чем converters, так как применяется на этапе загрузки.  

```converters={"col_name": func}``` Словарь (dict of functions) который применяется к данным в заданных колонках до их преобразования в dtype.  
Keys can either be integers or column labels.  
Подходит для сложных преобразований.  
Если для столбца определён ```converters```, то ```dtype``` для этого столбца будет проигнорирован.  
(If ```converters``` are specified, they will be applied **INSTEAD** of ```dtype``` conversion)

```python
import pandas as pd

# Указываем тип данных для столбцов
dtype_dict = {"col1": "int64", "col2": "float64", "col": "category"}

# Указываем конвертеры для строк
converters_dict = { "column4": lambda x: x.strip().lower() } 
# Пример преобразования строк в lowercase

df = pd.read_csv("file.csv", dtype=dtype_dict, converters=converters_dict)
```

### DataFrame.astype()
приведение столбцов к любому указанному типу данных

```python
import pandas as pd

df = pd.DataFrame({ 
    'A': [1, 2, 3, 4, 5],
    'B': ['a', 'b', 'c', 'd', 'e'],
    'C': [1.1, '1.0', '1.3', 2, 5]
})

# Convert all columns to string type
df = df.astype(str)
print(df.dtypes)
 ```
### DataFrame.astype()
Изменение определенных столбцов
```python
import pandas as pd

# Sample DataFrame
df = pd.DataFrame({
    'A': [1, 2, 3, 4, 5],
    'B': ['a', 'b', 'c', 'd', 'e'],
    'C': [1.1, '1.0', '1.3', 2, 5]
})

# Define the conversion dictionary
convert_dict = {'A': int, 'C': float}

# Convert columns using the dictionary
df = df.astype(convert_dict)
print(df.dtypes)
```

### DataFrame.apply()
Преобразование типов данных
```python
# importing pandas as pd
import pandas as pd

# sample dataframe
df = pd.DataFrame({
    'A': [1, 2, 3, '4', '5'],
    'B': ['a', 'b', 'c', 'd', 'e'],
    'C': [1.1, '2.1', 3.0, '4.1', '5.1']})

# using apply method
df[['A', 'C']] = df[['A', 'C']].apply(pd.to_numeric)
print(df.dtypes)
```

### DataFrame.infer_objects()
автоматически вывести тип данных столбцов, которые имеют тип объекта. 
```python
import pandas as pd

# Sample DataFrame with mixed object columns
df = pd.DataFrame({
    'A': [1, 2, 3, 4, 5],
    'B': ['a', 'b', 'c', 'd', 'e'],
    'C': [1.1, 2.1, 3.0, 4.1, 5.1]
}, dtype='object')

# Infer object types
df = df.infer_objects()
print(df.dtypes)
```

### convert_dtypes()
Автоматически преобразует столбцы в наиболее подходящий тип данных на основе имеющихся значений.   
Этот метод особенно полезен, когда вы хотите, чтобы Pandas обрабатывал преобразование на основе собственных правил вывода

```python
import pandas as pd

# Sample DataFrame
data = {
    "name": ["Aman", "Hardik", pd.NA],
    "qualified": [True, False, pd.NA]
}

df = pd.DataFrame(data)

print("Original Data Types:")
print(df.dtypes)

# Convert data types using convert_dtypes
newdf = df.convert_dtypes()

print(" \nNew Data Types:")
print(newdf.dtypes)
```