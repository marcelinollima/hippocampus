"""Start the server at login, for local (single-machine) installs.

Nothing here needs admin rights:
  Windows  a hidden launcher (.vbs) in the user's Startup folder
  macOS    a LaunchAgent in ~/Library/LaunchAgents
  Linux    a systemd user unit in ~/.config/systemd/user

Without this, a local server only runs while a terminal is open, and since the
recall hook fails silently, memory would just quietly stop working.
"""
import os
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape

from .config import HOME

LABEL = "io.github.marcelinollima.hippocampus"
LOG = HOME / "server.log"


def _env():
    # Settings exported in the current shell won't exist at login: carry them over.
    return {k: v for k, v in os.environ.items() if k.startswith("HIPPOCAMPUS_")}


def _command(python=None):
    return [python or sys.executable, "-m", "hippocampus.cli", "serve", "--log-file", str(LOG)]


def windows_file():
    return (Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
            / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "hippocampus.vbs")


def windows_script():
    # pythonw has no console window. In a venv, pythonw.exe is only a launcher
    # that falls back to the base python.exe (which opens a console) when the
    # base install has no pythonw.exe, so check the base too. Either way the
    # window style 0 below keeps a console hidden.
    exe = Path(sys.executable)
    base = Path(getattr(sys, "_base_executable", sys.executable))
    pyw = exe.with_name("pythonw.exe")
    use_pyw = pyw.exists() and base.with_name("pythonw.exe").exists()
    cmd = " ".join('""%s""' % a for a in _command(str(pyw if use_pyw else exe)))
    lines = ['Set sh = CreateObject("WScript.Shell")',
             'Set env = sh.Environment("PROCESS")']
    lines += ['env("%s") = "%s"' % (k, v.replace('"', '""')) for k, v in _env().items()]
    lines.append('sh.Run "%s", 0, False' % cmd)
    return "\r\n".join(lines) + "\r\n"


def mac_file():
    return Path.home() / "Library" / "LaunchAgents" / (LABEL + ".plist")


def mac_plist():
    args = "".join("<string>%s</string>" % escape(a) for a in _command())
    env = "".join("<key>%s</key><string>%s</string>" % (escape(k), escape(v))
                  for k, v in _env().items())
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
            '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0"><dict>'
            "<key>Label</key><string>%s</string>"
            "<key>ProgramArguments</key><array>%s</array>"
            "<key>EnvironmentVariables</key><dict>%s</dict>"
            "<key>RunAtLoad</key><true/><key>KeepAlive</key><true/>"
            "</dict></plist>\n" % (LABEL, args, env))


def linux_file():
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "systemd" / "user" / "hippocampus.service"


def linux_unit():
    q = lambda a: '"%s"' % a.replace("\\", "\\\\").replace('"', '\\"')  # noqa: E731
    env = "".join("Environment=%s\n" % q("%s=%s" % kv) for kv in _env().items())
    return ("[Unit]\nDescription=Hippocampus long-term memory\n\n"
            "[Service]\n%sExecStart=%s\nRestart=on-failure\nRestartSec=5\n\n"
            "[Install]\nWantedBy=default.target\n" % (env, " ".join(q(a) for a in _command())))


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    try:
        path.chmod(0o600)  # may carry HIPPOCAMPUS_TOKEN
    except OSError:
        pass
    return path


def _run(*cmd):
    return subprocess.run(list(cmd), capture_output=True, text=True)


def enable(start=True):
    HOME.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        path = _write(windows_file(), windows_script())
        if start:
            subprocess.Popen(["wscript", str(path)])
    elif sys.platform == "darwin":
        path = _write(mac_file(), mac_plist())
        if start:
            _run("launchctl", "unload", str(path))
            _run("launchctl", "load", "-w", str(path))
    else:
        path = _write(linux_file(), linux_unit())
        if start:
            _run("systemctl", "--user", "daemon-reload")
            _run("systemctl", "--user", "enable", "--now", "hippocampus.service")
    return path


def disable():
    if sys.platform == "win32":
        path = windows_file()
    elif sys.platform == "darwin":
        path = mac_file()
        if path.exists():
            _run("launchctl", "unload", "-w", str(path))
    else:
        path = linux_file()
        _run("systemctl", "--user", "disable", "--now", "hippocampus.service")
    if path.exists():
        path.unlink()
    return path
