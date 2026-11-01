"""Deterministic static analysis in a throw-away temp dir. Submitted code is never executed."""
import importlib.util
import json
import os
import shutil
import subprocess  # nosec B404
import sys
import tempfile
from pathlib import Path
from defusedxml import ElementTree as ET
from .schemas import Finding

try:  # POSIX only; absent on native Windows (there only the wall-clock timeout limits a run)
    import resource
except ImportError:  # pragma: no cover - exercised by tests via sys.modules patching
    resource = None

TOOLS = Path(os.environ.get("REVIEWAI_TOOLS_DIR", Path(__file__).resolve().parent.parent / "tools"))
ESLINT = TOOLS / "js" / "node_modules" / "eslint" / "bin" / "eslint.js"
ESLINT_CFG = TOOLS / "js" / "eslint.config.mjs"
CS_JAR = TOOLS / "java" / "checkstyle.jar"
CS_CFG = TOOLS / "java" / "checkstyle.xml"
TIMEOUT = 30
MAX_OUT = 2_000_000


def _clean_env(cwd: str, windows: bool | None = None) -> dict[str, str]:
    """Minimal environment: analyzers must never see our API keys/tokens."""
    env = {"PATH": os.environ.get("PATH", ""), "HOME": cwd, "LANG": "C.UTF-8"}
    is_windows = (os.name == "nt") if windows is None else windows
    if is_windows:  # Windows programs (python, node, java) fail to start without these variables
        for k in ("SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT"):
            if k in os.environ:
                env[k] = os.environ[k]
        env["TEMP"] = env["TMP"] = env["USERPROFILE"] = cwd
    return env


def _limit_resources(pid: int, cpu_seconds: int) -> None:
    """Best-effort CPU/file-size limits where the platform supports prlimit (Linux)."""
    if resource is None or not hasattr(resource, "prlimit"):
        return
    try:
        resource.prlimit(pid, resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        resource.prlimit(pid, resource.RLIMIT_FSIZE, (10_000_000, 10_000_000))
    except (OSError, ValueError):
        pass


def _run(argv: list[str], cwd: str, timeout: int = TIMEOUT) -> tuple[str, str]:
    # argv list, shell=False, fixed analyzers, our own temp files -> safe
    p = subprocess.Popen(  # nosec B603
        argv, cwd=cwd, env=_clean_env(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        encoding="utf-8", errors="replace", shell=False)
    _limit_resources(p.pid, timeout)
    try:
        out, err = p.communicate(timeout=timeout)  # wall-clock timeout works on every platform
    except subprocess.TimeoutExpired:
        p.kill()
        p.communicate()
        raise
    return out[:MAX_OUT], err[:MAX_OUT]


def _find(name: str, env_var: str, extras: list[str]) -> str | None:
    """Locate an executable: explicit env override, PATH, then well-known install locations."""
    override = os.environ.get(env_var)
    if override and Path(override).is_file():
        return override
    return shutil.which(name) or next((e for e in extras if Path(e).is_file()), None)


def _find_node() -> str | None:
    return _find("node", "NODE_PATH_EXE", [r"C:\Program Files\nodejs\node.exe"])


def _find_java() -> str | None:
    home = os.environ.get("JAVA_HOME")
    extras = [str(Path(home) / "bin" / ("java.exe" if os.name == "nt" else "java"))] if home else []
    return _find("java", "JAVA_EXE", extras)


def _find_cppcheck() -> str | None:
    return _find("cppcheck", "CPPCHECK_PATH", [r"C:\Program Files\Cppcheck\cppcheck.exe",
                                              r"C:\Program Files (x86)\Cppcheck\cppcheck.exe"])


def _py_mod(name: str):
    return None if importlib.util.find_spec(name) else f"{name} is not installed"


def _need(path: Path, label: str):
    return None if path.exists() else f"{label} not installed (run backend/tools/setup.sh)"


def _chk_eslint():
    return (None if _find_node() else "node is not installed") or _need(ESLINT, "ESLint") \
        or _need(ESLINT_CFG, "ESLint config")


def _chk_checkstyle():
    return (None if _find_java() else "java is not installed") or _need(CS_JAR, "Checkstyle")


def _chk_cppcheck():
    return None if _find_cppcheck() else "cppcheck is not installed (set CPPCHECK_PATH if it is not on PATH)"


def _f(analyzer, i, **kw) -> Finding:
    return Finding(id=f"{analyzer}-{i}", source="static_analysis", analyzer=analyzer, **kw)


def _ruff(d: str, fname: str) -> list[Finding]:
    out, _ = _run([sys.executable, "-m", "ruff", "check", "--output-format", "json", "--no-cache",
                   "--select", "E,F,B", fname], d)
    res = []
    for i, r in enumerate(json.loads(out or "[]")):
        code = r.get("code") or "syntax-error"
        res.append(_f("ruff", i, category="Maintainability", rule_id=code,
                      severity="Medium" if code.startswith("F") or code == "syntax-error" else "Low",
                      title=f"{code}: {r['message']}", description=r["message"],
                      line_start=r["location"]["row"], line_end=r["end_location"]["row"],
                      confidence="high", certainty="confirmed" if code == "syntax-error" else "possible"))
    return res


def _bandit(d: str, fname: str) -> list[Finding]:
    out, _ = _run([sys.executable, "-m", "bandit", "-f", "json", "-q", fname], d)
    sev = {"HIGH": "High", "MEDIUM": "Medium", "LOW": "Low"}
    conf = {"HIGH": "high", "MEDIUM": "medium", "LOW": "low"}
    return [_f("bandit", i, category="Security", rule_id=r["test_id"],
               severity=sev.get(r["issue_severity"], "Low"),
               title=f"{r['test_id']}: {r['test_name']}", description=r["issue_text"],
               line_start=r["line_number"], line_end=r["line_number"],
               confidence=conf.get(r["issue_confidence"], "low"))
            for i, r in enumerate(json.loads(out or "{}").get("results", []))]


def _eslint(d: str, fname: str) -> list[Finding]:
    out, _ = _run([_find_node(), str(ESLINT), "--config", str(ESLINT_CFG), "--no-config-lookup",
                   "--format", "json", "--no-warn-ignored", fname], d)
    msgs = json.loads(out)[0]["messages"]
    res = []
    for i, m in enumerate(msgs):
        rule = m.get("ruleId") or "parse-error"
        security = rule.startswith("security/") or rule in ("no-eval", "no-implied-eval", "no-new-func")
        res.append(_f("eslint", i, category="Security" if security else "Maintainability", rule_id=rule,
                      severity="Medium" if security or m.get("severity") == 2 else "Low",
                      title=f"{rule}: {m['message']}"[:300], description=m["message"],
                      line_start=m.get("line"), line_end=m.get("endLine") or m.get("line"),
                      confidence="high" if m.get("fatal") else "medium",
                      certainty="confirmed" if m.get("fatal") else "possible"))
    return res


def _checkstyle(d: str, fname: str) -> list[Finding]:
    out, _ = _run([_find_java(), "-Xmx256m", "-jar", str(CS_JAR), "-c", str(CS_CFG), "-f", "xml", fname], d)
    root = ET.fromstring(out)
    sev = {"error": "Medium", "warning": "Low", "info": "Informational"}
    res = []
    for i, e in enumerate(root.iter("error")):
        rule = (e.get("source") or "checkstyle").rsplit(".", 1)[-1]
        line = int(e.get("line")) if e.get("line") else None
        res.append(_f("checkstyle", i, category="Maintainability", rule_id=rule,
                      severity=sev.get(e.get("severity", "error"), "Low"),
                      title=f"{rule}: {e.get('message', '')}"[:300], description=e.get("message", ""),
                      line_start=line, line_end=line, confidence="medium"))
    return res


def _cppcheck(d: str, fname: str) -> list[Finding]:
    _, err = _run([_find_cppcheck(), "--enable=warning,style,performance,portability", "--language=c++",
                   "--template={line}|{severity}|{id}|{message}", "--quiet", fname], d)
    sev = {"error": "High", "warning": "Medium", "style": "Low", "performance": "Low",
           "portability": "Low", "information": "Informational"}
    res = []
    for line in err.split("\n"):
        parts = line.split("|", 3)
        if len(parts) != 4 or not parts[0].isdigit():
            continue
        ln, s, rid, msg = parts
        res.append(_f("cppcheck", len(res), category="Security" if s == "error" else "Maintainability",
                      rule_id=rid, severity=sev.get(s, "Low"), title=f"{rid}: {msg}"[:300], description=msg,
                      line_start=int(ln), line_end=int(ln), confidence="medium",
                      certainty="confirmed" if s == "error" else "possible"))
    return res


# language -> (filename, [(analyzer name, availability check, runner)])
REGISTRY = {
    "python": ("submission.py", [("ruff", lambda: _py_mod("ruff"), _ruff),
                                 ("bandit", lambda: _py_mod("bandit"), _bandit)]),
    "javascript": ("submission.js", [("eslint", _chk_eslint, _eslint)]),
    "typescript": ("submission.ts", [("eslint", _chk_eslint, _eslint)]),
    "java": ("Submission.java", [("checkstyle", _chk_checkstyle, _checkstyle)]),
    "cpp": ("submission.cpp", [("cppcheck", _chk_cppcheck, _cppcheck)]),
}


def availability() -> dict[str, dict[str, str]]:
    return {lang: {name: (chk() and f"unavailable: {chk()}") or "available" for name, chk, _ in specs}
            for lang, (_, specs) in REGISTRY.items()}


def analyze(code: str, language: str) -> tuple[list[Finding], dict[str, str]]:
    """Returns (findings, per-analyzer status). Status is 'ran' only if the tool really ran and parsed."""
    if language not in REGISTRY:
        return [], {"static_analysis": "not_supported_for_language"}
    fname, specs = REGISTRY[language]
    findings: list[Finding] = []
    status: dict[str, str] = {}
    with tempfile.TemporaryDirectory(prefix="reviewai_") as d:
        Path(d, fname).write_text(code, encoding="utf-8")
        for name, check, runner in specs:
            reason = check()
            if reason:
                status[name] = f"unavailable: {reason}"
                continue
            try:
                findings += runner(d, fname)
                status[name] = "ran"
            except subprocess.TimeoutExpired:
                status[name] = "timeout"
            except OSError:
                status[name] = "error: analyzer failed to start"
            except (ValueError, KeyError, IndexError, TypeError, ET.ParseError):
                status[name] = "error: could not parse analyzer output"
    for i, f in enumerate(findings):  # unique ids across analyzers
        f.id = f"{f.analyzer}-{i}"
    return findings, status
