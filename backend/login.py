"""One-time interactive Garmin login.

Run this once (locally, or on the host) to mint garth OAuth tokens for your
Garmin account and save them to disk. The backend then reads those tokens and
never needs your password again — until they expire (~1 year), when you re-run.

    uv run python login.py

If your account has MFA enabled, Garmin sends a code to your phone/email; enter
it when prompted. The password is used only to mint tokens via garth and is
never stored.
"""
import getpass
import os

import garmin

DEFAULT_TOKEN_FILE = "garmin_tokens.blob"


def obtain_token_blob(email, password, prompt_mfa, auth=garmin) -> str:
    """Drive the garth login, prompting for an MFA code only if Garmin asks.

    prompt_mfa is a zero-arg callable returning the code from the user's phone.
    """
    result = auth.begin_login(email, password)
    if result.needs_mfa:
        return auth.resume_login(result.mfa_context, prompt_mfa())
    return result.token_blob


def save_token_blob(blob: str, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(blob)
    os.chmod(path, 0o600)  # tokens are sensitive: owner read/write only


def main() -> None:
    path = os.environ.get("GARMIN_TOKEN_FILE", DEFAULT_TOKEN_FILE)
    email = input("Garmin email: ").strip()
    password = getpass.getpass("Garmin password: ")
    blob = obtain_token_blob(
        email, password,
        prompt_mfa=lambda: input("MFA code from your phone: ").strip(),
    )
    save_token_blob(blob, path)
    print(f"Saved Garmin tokens to {path}. The backend can now start.")


if __name__ == "__main__":
    main()
