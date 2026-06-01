```shell
IP='192.168.234.32' 
IP='192.168.208.236'
```

```shell
PORT='62224'
PORT='62225'
PORT='62226'
PORT='62227'
```

```shell
ENDPOINT='health'
ENDPOINT='ready'
```

```shell
curl -v http://${IP}:${PORT}/${ENDPOINT}
```

```shell
curl -v -s -X POST http://192.168.234.32:62228/mgmt \
  -H "Content-Type: application/json" \
  -d '[{"service": "tcp:62224", "mode": "http", "ruleset": "rules_200_ok"}]'
```

```shell
curl -v -s -X POST http://192.168.234.32:62228/mgmt \
  -H "Content-Type: application/json" \
  -d '[{"service": "tcp:62224", "mode": "http", "ruleset": "rules_200_fail"}]'
```

```shell
curl -v -s -X POST http://192.168.234.32:62228/mgmt \
  -H "Content-Type: application/json" \
  -d '[{"service": "tcp:62224", "mode": "http", "ruleset": "rules_200_maint"}]'
```
```shell
curl -v -s -X POST http://192.168.234.32:62228/mgmt \
  -H "Content-Type: application/json" \
  -d '[{"service": "tcp:62224", "mode": "http", "ruleset": "rules_200_ok_maint"}]'
```


```shell
curl -v -s -X POST http://192.168.234.32:62228/mgmt \
  -H "Content-Type: application/json" \
  -d '[{"service": "tcp:62224", "mode": "http", "ruleset": "rules_healthy"}]'
```

```shell
watch -n 1 "curl -v http://192.168.234.32:62224/health"
```