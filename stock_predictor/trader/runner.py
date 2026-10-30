"""Running the skill scripts for the web UI.

Each mode (demo, live) has its own working folder; the scripts read and write the
shared files in its trader/ subfolder. A run is a stream of small events (start,
output lines, files changed, end) that the page turns into a step-by-step view.
"""
import json
import math
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from .. import config
from .catalog import SETTINGS, SKILLS, SKILLS_BY_ID

MODES = ("demo", "live")
FIXTURES = config.SKILLS_DIR / "tests" / "fixtures"
EXAMPLE_CONFIG = config.SKILLS_DIR / "trader-budget" / "config.example.json"
READABLE = {".json", ".txt"}
MAX_READ_BYTES = 2_000_000

_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TEXT_RE = re.compile(r"^[\w .,'&:$@+()/\-]{1,120}$")

_locks = {m: threading.Lock() for m in MODES}
_running: dict[str, subprocess.Popen] = {}
_cancelled: set[str] = set()


class InputError(ValueError):
    """A request the UI should show back to the user (bad value, wrong mode...)."""


class Busy(RuntimeError):
    """Another skill is still running in this mode."""


# Workspace ----------------------------------------------------------------------

def _check_mode(mode: str) -> str:
    if mode not in MODES:
        raise InputError(f"Unknown mode '{mode}'.")
    return mode


def workspace(mode: str) -> Path:
    """The mode's working folder, with trader/config.json seeded from the pack's example."""
    ws = config.TRADER_WORKSPACE / _check_mode(mode)
    trader = ws / "trader"
    trader.mkdir(parents=True, exist_ok=True)
    cfg = trader / "config.json"
    if not cfg.exists():
        data = json.loads(EXAMPLE_CONFIG.read_text(encoding="utf-8"))
        data["sec_user_agent"] = ""  # the example's placeholder; live mode asks for the real one
        cfg.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return ws


def _trader_path(mode: str, rel: str) -> Path:
    """Resolve a path the page asked for, refusing anything outside trader/."""
    root = (workspace(mode) / "trader").resolve()
    rel = rel.removeprefix("trader/")
    target = (root / rel).resolve()
    if target != root and root not in target.parents:
        raise InputError("That file is outside the trader folder.")
    return target


def snapshot(mode: str) -> dict[str, tuple[int, int]]:
    root = workspace(mode) / "trader"
    return {p.relative_to(root.parent).as_posix(): (p.stat().st_mtime_ns, p.stat().st_size)
            for p in root.rglob("*") if p.is_file()}


def _changes(before: dict, after: dict) -> list[dict]:
    out = [{"path": p, "change": "created" if p not in before else "updated"}
           for p in sorted(after) if before.get(p) != after[p]]
    out += [{"path": p, "change": "deleted"} for p in sorted(before) if p not in after]
    return out


def state(mode: str) -> dict:
    root = workspace(mode) / "trader"
    files = [{"path": p, "size": size, "modified": mtime // 1_000_000}
             for p, (mtime, size) in sorted(snapshot(mode).items())]
    return {
        "mode": mode,
        "busy": _locks[mode].locked(),
        "done": {s.id: bool(s.output) and (root / s.output).exists() for s in SKILLS},
        "files": files,
        "settings": read_settings(mode),
        "sec_ready": _has_sec_identity(mode),
    }


def read_file(mode: str, rel: str) -> dict:
    path = _trader_path(mode, rel)
    if not path.is_file():
        raise InputError("That file does not exist (yet).")
    if path.suffix not in READABLE:
        raise InputError("Only .json and .txt files can be shown here.")
    if path.stat().st_size > MAX_READ_BYTES:
        raise InputError("That file is too big to show here.")
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".json":
        try:
            return {"path": rel, "kind": "json", "content": json.loads(text)}
        except ValueError:
            pass
    return {"path": rel, "kind": "text", "content": text}


def reset(mode: str) -> None:
    """Delete everything the skills wrote in this mode (the settings go back to the defaults)."""
    lock = _locks[_check_mode(mode)]
    if not lock.acquire(blocking=False):
        raise Busy("A skill is still running. Stop it first.")
    try:
        root = _trader_path(mode, "")
        shutil.rmtree(root, ignore_errors=True)
        workspace(mode)
    finally:
        lock.release()


# Values ----------------------------------------------------------------------

def parse_value(f, raw):
    """Validate one form value against its field. Returns None for "not given"."""
    if f.kind == "bool":
        if raw is None or raw == "":
            return bool(f.default)
        return raw is True or str(raw).lower() in ("true", "on", "1", "yes")
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        if f.required:
            raise InputError(f"{f.label}: please fill this in.")
        return None
    text = str(raw).strip()

    if f.kind == "ticker":
        value = text.upper()
        if not _TICKER_RE.match(value):
            raise InputError(f"{f.label}: '{text}' is not a ticker symbol.")
        return value
    if f.kind == "tickers":
        items = [t.upper() for t in re.split(r"[\s,;]+", text) if t]
        bad = [t for t in items if not _TICKER_RE.match(t)]
        if bad:
            raise InputError(f"{f.label}: '{bad[0]}' is not a ticker symbol.")
        if len(items) > 100:
            raise InputError(f"{f.label}: at most 100 tickers.")
        return items
    if f.kind in ("number", "int"):
        try:
            value = int(text) if f.kind == "int" else float(text)
        except ValueError:
            raise InputError(f"{f.label}: '{text}' is not a {'whole ' if f.kind == 'int' else ''}number.") from None
        if not math.isfinite(value):
            raise InputError(f"{f.label}: '{text}' is not a number.")
        if f.min is not None and value < f.min:
            raise InputError(f"{f.label}: must be at least {f.min:g}.")
        if f.max is not None and value > f.max:
            raise InputError(f"{f.label}: must be at most {f.max:g}.")
        return int(value) if f.kind == "number" and float(value).is_integer() else value
    if f.kind == "select":
        if text not in {str(v) for v, _ in f.choices}:
            raise InputError(f"{f.label}: '{text}' is not one of the choices.")
        return text
    if f.kind == "time":
        if not _TIME_RE.match(text):
            raise InputError(f"{f.label}: use HH:MM, e.g. 15:55.")
        return text
    if f.kind == "date":
        if not _DATE_RE.match(text):
            raise InputError(f"{f.label}: use YYYY-MM-DD.")
        return text
    if not _TEXT_RE.match(text) or text.startswith("-"):
        raise InputError(f"{f.label}: letters, numbers and simple punctuation only (max 120 characters).")
    return text


def _default(f, mode):
    return f.demo_default if mode == "demo" and f.demo_default is not None else f.default


def _show(f, value) -> str:
    if f.kind == "bool":
        return "yes" if value else "no"
    if f.kind == "select":
        return dict((str(k), v) for k, v in f.choices).get(str(value), str(value))
    if isinstance(value, list):
        return ", ".join(value)
    return str(value)


def build_command(skill, action, values: dict, mode: str) -> tuple[list[str], list[dict]]:
    """The argv for one action, plus the inputs in plain words for the page."""
    fix = str(FIXTURES)
    head = [sys.executable, "-I", "-X", "utf8", "-u", str(config.SKILLS_DIR / skill.script)]
    head += [a.replace("{fix}", fix) for a in action.args]
    positional, flags, parsed, inputs = [], [], {}, []

    for f in action.fields:
        if mode not in f.modes:
            continue
        v = parse_value(f, values.get(f.name, _default(f, mode)))
        parsed[f.name] = v
        if v is not None and not (f.kind == "bool" and not v and not f.when_false):
            inputs.append({"label": f.label, "value": _show(f, v)})
        if not f.arg or v is None:
            continue
        if f.kind == "bool":
            if v != f.when_false:
                flags.append(f.flag)
                if f.fmt != "{}":
                    flags.append(f.fmt)
            continue
        args = [",".join(v)] if f.kind == "tickers" and f.join else (v if f.kind == "tickers" else [f.fmt.format(v)])
        if f.flag:
            flags += [f.flag, *args]
        else:
            positional += args

    argv = head + positional + flags
    if mode == "demo":
        argv += [a.replace("{fix}", fix) for a in action.demo]
    if action.extra:
        argv += action.extra(parsed)
    return argv, inputs


def display_command(argv: list[str]) -> str:
    """The command as a person would type it, with local paths shortened."""
    skills = str(config.SKILLS_DIR)
    out = ["python"]
    for a in argv[5:]:  # skip the interpreter and its flags
        a = a.replace(str(FIXTURES), "<recorded data>").replace(skills, "vendor/day_trader_skill").replace("\\", "/")
        out.append(f'"{a}"' if " " in a else a)
    return " ".join(out)


# Settings ----------------------------------------------------------------------

def read_settings(mode: str) -> dict:
    cfg = json.loads((workspace(mode) / "trader" / "config.json").read_text(encoding="utf-8"))
    return {f.name: cfg.get(f.name) for f in SETTINGS}


def write_settings(mode: str, values: dict) -> dict:
    path = workspace(mode) / "trader" / "config.json"
    cfg = json.loads(path.read_text(encoding="utf-8"))
    for f in SETTINGS:
        if f.name not in values:
            continue
        v = parse_value(f, values[f.name])
        if f.name == "sec_user_agent" and v and ("@" not in v or " " not in v or "you@example.com" in v):
            raise InputError(f"{f.label}: write your name, a space, then your email, e.g. Jane Doe jane@example.com.")
        if v is None:
            v = [] if f.kind == "tickers" else "" if f.kind == "text" else f.default
        cfg[f.name] = v
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return read_settings(mode)


def _has_sec_identity(mode: str) -> bool:
    # Same rule as the skills: Settings, else the SEC_USER_AGENT environment variable.
    ua = str(read_settings(mode).get("sec_user_agent") or os.environ.get("SEC_USER_AGENT") or "")
    return "@" in ua and "you@example.com" not in ua


# Running ----------------------------------------------------------------------

def start(skill_id: str, action_id: str, values: dict, mode: str):
    """Validate the request and return the event stream. Raises before anything runs."""
    _check_mode(mode)
    skill = SKILLS_BY_ID.get(skill_id)
    action = next((a for a in skill.actions if a.id == action_id), None) if skill else None
    if not action:
        raise InputError("Unknown skill or action.")
    if mode not in action.modes:
        raise InputError(f"\"{action.label}\" only works in {' and '.join(action.modes)} mode.")
    if action.needs_sec and mode == "live" and not _has_sec_identity(mode):
        raise InputError("The SEC needs to know who is asking. Add your name and email in Settings first.")
    argv, inputs = build_command(skill, action, values or {}, mode)
    if _locks[mode].locked():
        raise Busy("Another skill is still running. Wait for it or press Stop.")
    return _stream(mode, argv, inputs)


def cancel(mode: str) -> bool:
    proc = _running.get(_check_mode(mode))
    if not proc or proc.poll() is not None:
        return False
    _cancelled.add(mode)
    proc.kill()
    return True


def _pump(pipe, name, q):
    for line in iter(pipe.readline, ""):
        q.put((name, line))
    q.put((name, None))


def _stream(mode: str, argv: list[str], inputs: list[dict]):
    lock = _locks[mode]
    if not lock.acquire(blocking=False):
        yield {"t": "error", "message": "Another skill is still running. Wait for it or press Stop."}
        return
    proc = None
    try:
        ws = workspace(mode)
        before = snapshot(mode)
        _cancelled.discard(mode)
        yield {"t": "start", "command": display_command(argv), "folder": f"trader_workspace/{mode}", "inputs": inputs}

        started = time.monotonic()
        proc = subprocess.Popen(
            argv, cwd=ws, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        _running[mode] = proc
        q: queue.Queue = queue.Queue()
        for pipe, name in ((proc.stdout, "out"), (proc.stderr, "err")):
            threading.Thread(target=_pump, args=(pipe, name, q), daemon=True).start()

        open_pipes, timed_out = 2, False
        while open_pipes:
            try:
                name, line = q.get(timeout=1.0)
            except queue.Empty:
                elapsed = time.monotonic() - started
                if elapsed > config.TRADER_MAX_RUN_SECONDS and not timed_out:
                    timed_out = True
                    proc.kill()
                yield {"t": "tick", "seconds": round(elapsed)}
                continue
            if line is None:
                open_pipes -= 1
            else:
                yield {"t": "line", "s": name, "text": line.rstrip("\r\n")}

        code = proc.wait()
        yield {"t": "files", "files": _changes(before, snapshot(mode))}
        yield {"t": "end", "code": code, "seconds": round(time.monotonic() - started, 1),
               "cancelled": mode in _cancelled, "timed_out": timed_out}
    except OSError as exc:
        yield {"t": "error", "message": f"Could not start the skill: {exc}"}
    finally:
        if proc and proc.poll() is None:
            proc.kill()
            proc.wait()
        _running.pop(mode, None)
        lock.release()


def market_clock() -> dict | None:
    """The NYSE clock from trader-alerts (no network needed)."""
    script = config.SKILLS_DIR / "trader-alerts" / "alerts.py"
    try:
        out = subprocess.run([sys.executable, "-I", "-X", "utf8", str(script), "clock", "--json"],
                             cwd=workspace("live"), capture_output=True, text=True, encoding="utf-8", timeout=15,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return json.loads(out.stdout)
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
