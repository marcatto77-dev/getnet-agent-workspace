# Alertas sugeridos

- Erros HTTP 5xx acima de 2% por cinco minutos.
- Latência p95 do chat acima de 8 segundos por dez minutos.
- Espera de handoff acima de 10 minutos ou fila acima de 10 clientes.
- Bloqueios de guardrail acima de três vezes a linha de base por 15 minutos.
- Orçamento diário de tokens de qualquer cliente acima de 80% e gasto global acima do limite definido.

`/metrics` é Prometheus text format e exige `X-Metrics-Token` quando `METRICS_TOKEN` estiver configurado. Sem token, aceita apenas origem loopback/rede privada do proxy interno.
