import plistlib

from hippocampus import autostart
from hippocampus.cli import main
from hippocampus.config import Config


def test_init_creates_token_and_folder(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("HIPPOCAMPUS_TOKEN", raising=False)
    monkeypatch.setenv("HIPPOCAMPUS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("HIPPOCAMPUS_TOKEN_FILE", str(tmp_path / "server-token"))
    main(["init"])
    assert (tmp_path / "data" / "memories").is_dir()
    token = (tmp_path / "server-token").read_text().strip()
    assert len(token) > 30
    # the server picks it up without any environment variable
    assert Config.from_env().token == token
    # running init again keeps the same token
    main(["init"])
    assert (tmp_path / "server-token").read_text().strip() == token
    assert "already set" in capsys.readouterr().out


def test_launchers_run_serve_with_log_and_carry_settings(monkeypatch):
    monkeypatch.setenv("HIPPOCAMPUS_OWNER", 'Ana "A"')
    unit = autostart.linux_unit()
    assert "hippocampus.cli" in unit and "--log-file" in unit
    assert 'Environment="HIPPOCAMPUS_OWNER=Ana \\"A\\""' in unit

    plist = plistlib.loads(autostart.mac_plist().encode())
    assert plist["ProgramArguments"][1:4] == ["-m", "hippocampus.cli", "serve"]
    assert plist["EnvironmentVariables"]["HIPPOCAMPUS_OWNER"] == 'Ana "A"'
    assert plist["RunAtLoad"] and plist["KeepAlive"]

    vbs = autostart.windows_script()
    assert 'env("HIPPOCAMPUS_OWNER") = "Ana ""A"""' in vbs
    assert ", 0, False" in vbs  # hidden window, don't wait
