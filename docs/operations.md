# Operations

## Local run

- Configure settings in `config/config.yaml` (copy from `config/config.example.yaml`).
- Ensure Redis is running if Redis sink is enabled.
- Start the component:

```bash
make run
```

## Health

The service emits `HealthEvent` DomainEvents for:
- WebSocket reconnects
- Catalog refresh durations
- Subscription changes

## Logs

Structured JSON logs by default. Adjust level via `logging.level` or `PME__LOGGING__LEVEL`.
