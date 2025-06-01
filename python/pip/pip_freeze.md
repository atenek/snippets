# pip freeze

```bash
python -m pip freeze # Generate output suitable for a requirements file.
```

```bash
# Generate a requirements file
env1/bin/python -m pip freeze > requirements.txt 
 
# install  in another environment.
env2/bin/python -m pip install -r requirements.txt 
```
