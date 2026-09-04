import asyncio
import sys

import httpx
import pytest

from httpxgen.generator import GenerationError
from httpxgen.output import write_client


def test_write_client_creates_an_importable_package(tmp_path, generatable_spec):
    package_dir = tmp_path / "payments"

    changed = write_client(spec=generatable_spec, package_dir=package_dir)

    assert {path.name for path in changed} == {
        "__init__.py",
        "serialization.py",
        "client.py",
        "exceptions.py",
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
