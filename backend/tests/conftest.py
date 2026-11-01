import os
import tempfile
from pathlib import Path
import pytest

os.environ["REVIEWAI_SKIP_DOTENV"] = "1"  # a developer's real backend/.env must never leak into tests
os.environ.setdefault("DATABASE_URL", f"sqlite:///{Path(tempfile.mkdtemp(), 'c.db').as_posix()}")
for _k in ("GEMINI_API_KEY", "GEMINI_MODEL", "ANTHROPIC_API_KEY", "GITHUB_WEBHOOK_SECRET", "GITHUB_WEBHOOK_TOKEN", "GITHUB_CLIENT_ID"):
    os.environ.pop(_k, None)


def pytest_configure(config):
    config.addinivalue_line("markers", "real_analyzers: use the real analyzer registry (skips if tools are absent)")


@pytest.fixture(autouse=True)
def deterministic_python_analyzers(request, monkeypatch):
    """Tests must not depend on Ruff/Bandit being installed, so by default the Python analyzers are replaced
    with tiny deterministic fakes that behave like them (a B307-style finding for eval(), F401 for `import os`).
    Tests that exercise the real tools opt out with @pytest.mark.real_analyzers."""
    if request.node.get_closest_marker("real_analyzers"):
        return
    from app import analysis

    def fake_ruff(d, fname):
        lines = Path(d, fname).read_text(encoding="utf-8").split("\n")
        return [analysis._f("ruff", i, category="Maintainability", rule_id="F401", severity="Medium",
                            title="F401: `os` imported but unused", description="`os` imported but unused",
                            line_start=n, line_end=n, confidence="high")
                for i, n in enumerate([n for n, t in enumerate(lines, 1) if t.strip() == "import os"])]

    def fake_bandit(d, fname):
        lines = Path(d, fname).read_text(encoding="utf-8").split("\n")
        return [analysis._f("bandit", i, category="Security", rule_id="B307", severity="Medium",
                            title="B307: blacklist", description="Use of possibly insecure function eval.",
                            line_start=n, line_end=n, confidence="high")
                for i, n in enumerate([n for n, t in enumerate(lines, 1) if "eval(" in t])]

    monkeypatch.setitem(analysis.REGISTRY, "python", ("submission.py", [
        ("ruff", lambda: None, fake_ruff), ("bandit", lambda: None, fake_bandit)]))
