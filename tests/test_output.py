import asyncio
import importlib.util
import sys

import httpx
import pytest

from httpxgen.generator import GenerationError
from httpxgen.output import write_client
from httpxgen.selection import filter_operations_by_tags


def test_layout_change_detects_and_removes_only_obsolete_generated_files(
    tmp_path, generatable_spec
):
    package_dir = tmp_path / "payments"
    write_client(
        spec=generatable_spec,
        package_dir=package_dir,
        tags=["payments", "invoices"],
    )
    obsolete = package_dir / "invoices" / "client.py"
    assert obsolete.exists()
    handwritten = package_dir / "invoices" / "custom.py"
    handwritten.write_text("value = 42\n")
    handwritten_init = package_dir / "manual" / "__init__.py"
    handwritten_init.parent.mkdir()
    handwritten_init.write_text("# handwritten\n")
    marker = package_dir / "manual" / "py.typed"
    marker.write_text("partial\n")
    binary = package_dir / "asset.bin"
    binary.write_bytes(b"\xff\x00")
    before = {p: p.read_bytes() for p in package_dir.rglob("*") if p.is_file()}
    selected = filter_operations_by_tags(generatable_spec, ["payments"])

    with pytest.raises(GenerationError, match=r"invoices.*client.py"):
        write_client(spec=selected, package_dir=package_dir, check=True)
    assert {p: p.read_bytes() for p in before} == before

    changed = write_client(spec=selected, package_dir=package_dir)
    assert obsolete in changed
    assert not obsolete.exists()
    assert handwritten.read_text() == "value = 42\n"
    assert handwritten_init.read_text() == "# handwritten\n"
    assert marker.read_text() == "partial\n"
    assert binary.read_bytes() == b"\xff\x00"
    package = _import_generated_package(tmp_path, "payments")
    http_client = httpx.AsyncClient()
    try:
        client = package.PaymentsClient(http_client, "https://example.test")
        assert callable(client.create_charge)
        assert importlib.util.find_spec("payments.invoices.client") is None
    finally:
        asyncio.run(http_client.aclose())
        _forget_generated_package(tmp_path, "payments")
    assert write_client(spec=selected, package_dir=package_dir, check=True) == []


def test_write_client_creates_an_importable_package(tmp_path, generatable_spec):
    package_dir = tmp_path / "payments"

    changed = write_client(spec=generatable_spec, package_dir=package_dir)

    assert {path.name for path in changed} == {
        "__init__.py",
        "serialization.py",
        "client.py",
        "exceptions.py",
        "http_methods.py",
        "transport.py",
        "models.py",
        "py.typed",
    }
    package = _import_generated_package(tmp_path, "payments")
    http_client = httpx.AsyncClient()
    client = package.PaymentsClient(
        http_client,
        "https://payments.example.com/api/",
    )
    try:
        assert callable(client.create_charge)
        assert package.PaymentMethod is not None
    finally:
        asyncio.run(http_client.aclose())
        _forget_generated_package(tmp_path, "payments")


def test_check_accepts_current_output(tmp_path, generatable_spec):
    package_dir = tmp_path / "payments"
    write_client(spec=generatable_spec, package_dir=package_dir)

    changed = write_client(spec=generatable_spec, package_dir=package_dir, check=True)

    assert changed == []


def test_check_reports_stale_generated_output(tmp_path, generatable_spec):
    package_dir = tmp_path / "payments"
    write_client(spec=generatable_spec, package_dir=package_dir)
    with (package_dir / "client.py").open("a") as client_module:
        client_module.write("# stale\n")

    with pytest.raises(GenerationError, match="generated client is stale"):
        write_client(
            spec=generatable_spec,
            package_dir=package_dir,
            check=True,
        )


def test_write_client_refuses_to_replace_handwritten_modules(
    tmp_path,
    generatable_spec,
):
    package_dir = tmp_path / "payments"
    package_dir.mkdir()
    (package_dir / "client.py").write_text("# handwritten\n")

    with pytest.raises(GenerationError, match="refusing to overwrite"):
        write_client(spec=generatable_spec, package_dir=package_dir)


def test_write_client_preserves_a_handwritten_package_init(
    tmp_path,
    generatable_spec,
):
    package_dir = tmp_path / "payments"
    package_dir.mkdir()
    package_init = package_dir / "__init__.py"
    package_init.write_text("# handwritten\n")

    changed = write_client(spec=generatable_spec, package_dir=package_dir)

    assert package_init.read_text() == "# handwritten\n"
    assert package_init not in changed


def _import_generated_package(parent, package_name):
    sys.path.insert(0, str(parent))
    return __import__(package_name)


def _forget_generated_package(parent, package_name):
    sys.path.remove(str(parent))
    for name in tuple(sys.modules):
        if name == package_name or name.startswith(f"{package_name}."):
            del sys.modules[name]
