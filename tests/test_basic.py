from httpxgen import main


def test_main_runs(capsys):
    main()
    captured = capsys.readouterr()
    assert "Hello from httpxgen!" in captured.out
