from collections.abc import Mapping, Sequence
from pathlib import Path

from httpxgen.generator import GenerationError, generate_client, generate_workspace
from httpxgen.generator.build import HttpClientBackend
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
    client_name: str | None = None,
    tags: Sequence[str] = (),
    schema_tags: Sequence[str] = (),
    http_client: HttpClientBackend = "protocol",
    check: bool = False,
) -> list[Path]:
    name = package_name or package_dir.name
    if client_name is not None and len(tags) > 1:
        raise GenerationError(
            "client_name cannot be used with multi-tag generation; client names "
            "are derived from tags"
        )
    rendered = (
        generate_workspace(
            spec,
            tags,
            name,
            schema_tags=schema_tags,
            http_client=http_client,
        )
        if len(tags) > 1
        else generate_client(
            spec,
            name,
            client_name=client_name,
            http_client=http_client,
        )
    )
    output = _managed_output(package_dir, rendered)
    obsolete = _obsolete_files(package_dir, rendered)
    changed = _changed_files(package_dir, output) + obsolete

    if check:
        if changed:
            paths = ", ".join(str(path) for path in changed)
            raise GenerationError(f"generated client is stale: {paths}")
        return []

    for relative, content in output.items():
        path = package_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    for path in obsolete:
        path.unlink()
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
        if path.is_symlink() or not path.resolve().is_relative_to(
            package_dir.resolve()
        ):
            raise GenerationError(
                f"refusing to write through a linked output path: {path}"
            )
        if not path.exists() or _is_generated(path) or path.read_text() == content:
            output[relative] = content
        elif not _is_preserved(relative):
            raise GenerationError(f"refusing to overwrite non-generated file: {path}")
    return output


def _is_generated(path: Path) -> bool:
    try:
        return path.read_text().startswith(GENERATED_HEADER)
    except (OSError, UnicodeError):
        return False


def _obsolete_files(package_dir: Path, rendered: Mapping[str, str]) -> list[Path]:
    root = package_dir.resolve()
    return sorted(
        path
        for path in package_dir.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and path.resolve().is_relative_to(root)
        and path.relative_to(package_dir).as_posix() not in rendered
        and _is_generated(path)
    )
