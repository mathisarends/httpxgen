# httpxgen

## Conventions

- In `__init__.py` files, use relative imports (e.g. `from .generator import ...`). Everywhere else, use absolute imports (`from httpxgen.generator import ...`).
- No blanket module-level docstrings/comments at the top of files (e.g. `"""Renders a typed async httpx client..."""`).
