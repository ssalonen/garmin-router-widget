"""Tests for the one-time login bootstrap (login.py).

The garth seam is faked; these cover the branching that matters: MFA is only
prompted when Garmin asks for it, and the returned blob is what gets persisted.
"""
import login
from garmin import LoginResult


class FakeAuth:
    def __init__(self, *, mfa=False):
        self._mfa = mfa
        self.begin_args = None
        self.resumed_with = None

    def begin_login(self, email, password):
        self.begin_args = (email, password)
        if self._mfa:
            return LoginResult(mfa_context=("live-client", {"csrf": "x"}))
        return LoginResult(token_blob=f"blob::{email}")

    def resume_login(self, mfa_context, code):
        self.resumed_with = (mfa_context, code)
        return "blob::after-mfa"


def test_obtain_token_blob_without_mfa_skips_prompt():
    auth = FakeAuth(mfa=False)
    prompts = []
    blob = login.obtain_token_blob(
        "rider@example.com", "pw",
        prompt_mfa=lambda: prompts.append("called") or "000000",
        auth=auth,
    )
    assert blob == "blob::rider@example.com"
    assert auth.begin_args == ("rider@example.com", "pw")
    assert prompts == []  # MFA never prompted


def test_obtain_token_blob_with_mfa_prompts_and_resumes():
    auth = FakeAuth(mfa=True)
    blob = login.obtain_token_blob(
        "rider@example.com", "pw",
        prompt_mfa=lambda: "123456",
        auth=auth,
    )
    assert blob == "blob::after-mfa"
    assert auth.resumed_with == (("live-client", {"csrf": "x"}), "123456")


def test_save_token_blob_writes_file_restrictively(tmp_path):
    path = tmp_path / "garmin_tokens.blob"
    login.save_token_blob("THE-BLOB", str(path))
    assert path.read_text() == "THE-BLOB"
    # tokens are sensitive → owner-only permissions
    assert (path.stat().st_mode & 0o077) == 0
