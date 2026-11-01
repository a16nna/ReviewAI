import os
from app.config import load_dotenv


def test_dotenv_loader_parses_quotes_comments_and_never_overrides(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text(
        '# comment\nRA_TEST_A=plain\nRA_TEST_B="quoted value"\nRA_TEST_C=\nRA_TEST_D=from-file\nbad line\n',
        encoding="utf-8-sig",
    )
    monkeypatch.delenv("REVIEWAI_SKIP_DOTENV")
    monkeypatch.setenv("RA_TEST_D", "from-environment")
    try:
        assert sorted(load_dotenv(f)) == ["RA_TEST_A", "RA_TEST_B"]
        assert os.environ["RA_TEST_B"] == "quoted value" and "RA_TEST_C" not in os.environ
        assert os.environ["RA_TEST_D"] == "from-environment"  # real environment wins
    finally:
        for k in ("RA_TEST_A", "RA_TEST_B", "RA_TEST_C"):
            os.environ.pop(k, None)


def test_loader_can_be_disabled(tmp_path):
    f = tmp_path / ".env"
    f.write_text("RA_TEST_Z=1\n")
    assert load_dotenv(f) == [] and "RA_TEST_Z" not in os.environ  # REVIEWAI_SKIP_DOTENV=1 in tests
