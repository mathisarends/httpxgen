import json
import sys

import pytest

from httpxgen.cli import main


def test_main_generates_a_package(tmp_path, monkeypatch, capsys):
    spec_path = tmp_path / "openapi.json"
    output_path = tmp_path / "generated_client"
    spec_path.write_text(json.dumps({"openapi": "3.1.0", "paths": {}}))
    monkeypatch.setattr(sys, "argv", ["httpxgen", str(spec_path), str(output_path)])

    result = main()

    assert result == 0
    assert "Generated 6 file(s)" in capsys.readouterr().out
    assert (output_path / "client.py").exists()


def test_main_reports_invalid_documents(tmp_path, monkeypatch, capsys):
    spec_path = tmp_path / "openapi.json"
    spec_path.write_text(json.dumps({"openapi": "2.0", "paths": {}}))
    monkeypatch.setattr(
        sys,
        "argv",
        ["httpxgen", str(spec_path), str(tmp_path / "generated_client")],
    )

    with pytest.raises(SystemExit) as exit_info:
        main()

    assert exit_info.value.code == 1
    assert "only OpenAPI 3.0 and 3.1" in capsys.readouterr().err


def test_main_check_mode_accepts_current_output(tmp_path, monkeypatch, capsys):
    spec_path = tmp_path / "openapi.json"
    output_path = tmp_path / "generated_client"
    spec_path.write_text(json.dumps({"openapi": "3.1.0", "paths": {}}))
    base_arguments = ["httpxgen", str(spec_path), str(output_path)]
    monkeypatch.setattr(sys, "argv", base_arguments)
    main()
    capsys.readouterr()
    monkeypatch.setattr(sys, "argv", [*base_arguments, "--check"])

    result = main()

    assert result == 0
    assert capsys.readouterr().out == "Generated HTTP client is current.\n"
