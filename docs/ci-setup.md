# CI Setup

## Required services

- Redis (for integration tests when enabled)

## Commands

```bash
make lint
make test
```

## Notes

- Use `uv` to install dependencies in CI.
- Prefer `uv pip install -e .[dev]` for reproducible environments.
