"""Key ID and Issuer ID come from a .env file, not from the UI."""

import pytest

from appstore_snapshots.connect import env
from appstore_snapshots.errors import CredentialsError


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch, tmp_path):
    for name in (env.KEY_ID, env.ISSUER_ID, env.KEY_PATH, env.BUNDLE_ID):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(env, "_loaded_from", None)
    # Point the "installed CLI run from elsewhere" fallback at an empty directory,
    # so a developer's own .env at the real project root cannot leak into a test.
    monkeypatch.setattr(env, "PROJECT_ROOT", tmp_path / "nowhere")


def write_env(folder, body: str):
    (folder / ".env").write_text(body)
    return folder / ".env"


def test_loads_values_from_a_dotenv_file(tmp_path, monkeypatch):
    write_env(tmp_path, "ASC_KEY_ID=ABCD123456\nASC_ISSUER_ID=69a6de70-uuid\n")
    monkeypatch.chdir(tmp_path)

    assert env.load() == tmp_path / ".env"
    assert env.require_key_and_issuer() == ("ABCD123456", "69a6de70-uuid")
    assert env.source() == tmp_path / ".env"


def test_comments_and_blank_values_are_handled(tmp_path, monkeypatch):
    write_env(
        tmp_path,
        "# a comment\nASC_KEY_ID=ABCD123456\n\nASC_ISSUER_ID=uuid\nASC_BUNDLE_ID=com.example.app\n",
    )
    monkeypatch.chdir(tmp_path)
    env.load()
    assert env.get(env.BUNDLE_ID) == "com.example.app"
    assert env.get(env.KEY_PATH) == ""  # absent -> empty, never a KeyError


def test_real_environment_wins_over_the_file(tmp_path, monkeypatch):
    write_env(tmp_path, "ASC_KEY_ID=FROM-FILE\nASC_ISSUER_ID=uuid\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(env.KEY_ID, "FROM-SHELL")

    env.load()
    assert env.require_key_and_issuer()[0] == "FROM-SHELL"


def test_missing_values_say_what_to_add_and_where(tmp_path, monkeypatch):
    write_env(tmp_path, "ASC_KEY_ID=ABCD123456\n")
    monkeypatch.chdir(tmp_path)
    env.load()

    with pytest.raises(CredentialsError) as excinfo:
        env.require_key_and_issuer()
    message = str(excinfo.value)
    assert "ASC_ISSUER_ID" in message
    assert "ASC_KEY_ID" not in message  # that one was fine
    assert ".env" in message


def test_no_dotenv_file_at_all(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    env.load()
    with pytest.raises(CredentialsError, match="ASC_KEY_ID and ASC_ISSUER_ID"):
        env.require_key_and_issuer()


def test_example_file_lists_every_setting():
    from pathlib import Path

    example = Path(__file__).resolve().parents[1] / ".env.example"
    text = example.read_text()
    for name in (env.KEY_ID, env.ISSUER_ID, env.KEY_PATH, env.BUNDLE_ID):
        assert name in text


def test_project_root_is_the_fallback_when_cwd_has_no_dotenv(tmp_path, monkeypatch):
    root = tmp_path / "project"
    root.mkdir()
    write_env(root, "ASC_KEY_ID=FROM-ROOT\nASC_ISSUER_ID=uuid\n")
    monkeypatch.setattr(env, "PROJECT_ROOT", root)

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    assert env.load() == root / ".env"
    assert env.require_key_and_issuer()[0] == "FROM-ROOT"
