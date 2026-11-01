import importlib
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import pytest
from app import analysis

pytestmark = pytest.mark.real_analyzers

AV = analysis.availability()
CASES = [("python", "x = eval(input())\n", "B307"), ("javascript", "var x = eval(prompt());\n", "no-eval"),
         ("typescript", "const y: number = eval('1');\n", "no-eval"),
         ("java", 'public class A { void f(){ try { } catch (Exception e) { } } }\n', "EmptyCatchBlockCheck"),
         ("cpp", "#include <cstring>\nint main(){ char b[2]; strcpy(b,\"hello\"); }\n", "bufferAccessOutOfBounds")]


@pytest.mark.parametrize("lang,code,rule", CASES)
def test_each_language_analyzer(lang, code, rule):
    if any("unavailable" in v for v in AV[lang].values()):
        pytest.skip(f"analyzer for {lang} not installed: {AV[lang]}")
    findings, status = analysis.analyze(code, lang)
    assert all(v == "ran" for v in status.values()), status
    assert any(x.rule_id == rule and x.source == "static_analysis" and x.line_start for x in findings)


def test_unavailable_analyzer_is_reported_not_faked(monkeypatch):
    monkeypatch.setattr(analysis, "CS_JAR", analysis.TOOLS / "nope.jar")
    findings, status = analysis.analyze("class A {}", "java")
    assert status["checkstyle"].startswith("unavailable") and findings == []


def test_timeout_and_garbage_output(monkeypatch):
    monkeypatch.setattr(analysis, "_py_mod", lambda name: None)  # pretend installed: only _run behaviour is under test

    def slow(*a, **k):
        raise subprocess.TimeoutExpired("x", 1)
    monkeypatch.setattr(analysis, "_run", slow)
    assert analysis.analyze("x=1", "python")[1] == {"ruff": "timeout", "bandit": "timeout"}
    monkeypatch.setattr(analysis, "_run", lambda *a, **k: ("garbage", ""))
    assert analysis.analyze("x=1", "python")[1]["ruff"].startswith("error")


def test_analyzers_do_not_inherit_secrets(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "sk-should-not-leak")
    probe = "import os;print(os.environ.get('GEMINI_API_KEY'))"
    out, _ = analysis._run([sys.executable, "-c", probe], str(tmp_path))
    assert out.strip() == "None"


def test_submitted_code_is_never_executed():
    if any("unavailable" in v for v in AV["python"].values()):
        pytest.skip("needs the real Python analyzers installed to be meaningful")
    marker = str(Path(tempfile.gettempdir()) / "reviewai_pwn_marker")
    if os.path.exists(marker):
        os.remove(marker)
    analysis.analyze(f"open({marker!r}, 'w').write('x')\n", "python")
    assert not os.path.exists(marker)


def test_unsupported_language():
    assert analysis.analyze("x", "cobol")[1] == {"static_analysis": "not_supported_for_language"}


def test_missing_ruff_and_bandit_are_reported_unavailable_not_successful(monkeypatch):
    monkeypatch.setattr(analysis, "_py_mod", lambda name: f"{name} is not installed")
    findings, status = analysis.analyze("x = eval(input())\n", "python")
    assert findings == []
    assert status == {"ruff": "unavailable: ruff is not installed", "bandit": "unavailable: bandit is not installed"}
    assert all(v != "ran" for v in status.values())
    assert analysis.availability()["python"]["ruff"].startswith("unavailable")


def test_review_api_still_works_when_python_analyzers_are_missing(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    monkeypatch.setattr(analysis, "_py_mod", lambda name: f"{name} is not installed")
    c = TestClient(app)
    body = c.post("/reviews", json={"code": "x = eval(input())\n", "language": "python"}).json()
    assert all(v.startswith("unavailable") for v in body["analyzers"].values())
    assert [f["source"] for f in body["findings"]] == ["ai"]  # only the (mock) AI notice; no fake static results
    assert c.get("/capabilities").json()["languages"]["python"]["bandit"].startswith("unavailable")


def test_module_imports_and_runs_without_the_resource_module(monkeypatch):
    """Native Windows has no `resource` module: importing must not fail and analysis must still work."""
    monkeypatch.setitem(sys.modules, "resource", None)  # makes `import resource` raise ImportError
    mod = importlib.reload(analysis)
    try:
        assert mod.resource is None
        mod._limit_resources(os.getpid(), 5)  # no-op
        _, status = mod.analyze("x = 1\n", "python")
        assert set(status) == {"ruff", "bandit"}
    finally:
        monkeypatch.undo()
        importlib.reload(analysis)
    assert analysis.resource is not None or os.name == "nt"


def test_wall_clock_timeout_applies_even_without_resource_limits(monkeypatch, tmp_path):
    monkeypatch.setattr(analysis, "resource", None)
    start = time.time()
    with pytest.raises(subprocess.TimeoutExpired):
        analysis._run([sys.executable, "-c", "import time; time.sleep(30)"], str(tmp_path), timeout=1)
    assert time.time() - start < 10


def test_windows_environment_keeps_system_vars_but_no_secrets(monkeypatch, tmp_path):
    monkeypatch.setenv("SYSTEMROOT", r"C:\Windows")
    monkeypatch.setenv("GEMINI_API_KEY", "sk-nope")
    env = analysis._clean_env(str(tmp_path), windows=True)
    assert env["SYSTEMROOT"] == r"C:\Windows" and env["TEMP"] == env["TMP"] == str(tmp_path)
    assert "GEMINI_API_KEY" not in env and "sk-nope" not in env.values()
    assert "SYSTEMROOT" not in analysis._clean_env(str(tmp_path), windows=False)


def test_executable_discovery_honours_overrides(monkeypatch, tmp_path):
    fake = tmp_path / "cppcheck.exe"
    fake.write_text("")
    monkeypatch.setenv("CPPCHECK_PATH", str(fake))
    assert analysis._find_cppcheck() == str(fake)
    monkeypatch.setenv("CPPCHECK_PATH", str(tmp_path / "missing.exe"))
    assert analysis._find_cppcheck() != str(tmp_path / "missing.exe")


def test_non_utf8_analyzer_output_does_not_crash(tmp_path):
    probe = "import sys; sys.stdout.buffer.write(b'\\xff\\xfe ok')"
    out, _ = analysis._run([sys.executable, "-c", probe], str(tmp_path))
    assert out.endswith("ok")
