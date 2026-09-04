from collections.abc import Mapping, Sequence
from pathlib import Path

from httpxgen.generator import GenerationError, generate_client, generate_workspace
from httpxgen.generator.templates import GENERATED_HEADER
from httpxgen.openapi import OpenAPISpec

_PRESERVE_IF_UNMANAGED = {"__init__.py", "py.typed"}


def _is_preserved(relative: str) -> bool:
    return relative.rsplit("/", 1)[-1] in _PRESERVE_IF_UNMANAGED


def write_client(
    *,
    spec: OpenAPISpec,
    package_dir: Path,
    package_name: str | None = None,
    tags: Sequence[str] = (),
    schema_tags: Sequence[str] = (),
    check: bool = False,
) -> list[Path]:
    name = package_name or package_dir.name
    rendered = (
        generate_workspace(spec, tags, name, schema_tags=schema_tags)
        if len(tags) > 1
        else generate_client(spec, name)
    )
    output = _managed_output(package_dir, rendered)
    changed = _changed_files(package_dir, output)

    if check:
        if changed:
            paths = ", ".join(str(path) for path in changed)
            raise GenerationError(f"generated client is stale: {paths}")
        return []

    for relative, content in output.items():
        path = package_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return changed


def _changed_files(package_dir: Path, output: Mapping[str, str]) -> list[Path]:
    return [
        path
        for relative, content in output.items()
        if not (path := package_dir / relative).exists() or path.read_text() != content
    ]


def _managed_output(package_dir: Path, rendered: Mapping[str, str]) -> dict[str, str]:
    output: dict[str, str] = {}
    for relative, content in rendered.items():
        path = package_dir / relative
        if not path.exists() or _is_generated(path) or path.read_text() == content:
            output[relative] = content
        elif not _is_preserved(relative):
            raise GenerationError(f"refusing to overwrite non-generated file: {path}")
    return output


def _is_generated(path: Path) -> bool:
    return path.read_text().startswith(GENERATED_HEADER)
