"""Minimal self-contained HTML for the /setup bootstrap pages.

Rendered inside the phone webview during Garmin sign-in. All interpolated
values are HTML-escaped (reflected-input guard).
"""
import html

_STYLE = (
    "body{font-family:sans-serif;max-width:22rem;margin:2rem auto;padding:0 1rem}"
    "input{width:100%;padding:.6rem;margin:.4rem 0;box-sizing:border-box}"
    "button{width:100%;padding:.7rem;font-size:1rem}.err{color:#b00}"
)


def login_form(token: str, error: str = "") -> str:
    token = html.escape(token, quote=True)  # reflected into a value="" attribute
    err = f'<p class="err">{html.escape(error)}</p>' if error else ""
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Connect your Garmin account</title><style>{_STYLE}</style></head>
<body><h2>Connect your Garmin account</h2>{err}
<form method="post" action="/setup/login">
<input type="email" name="email" placeholder="Garmin email" required autofocus>
<input type="password" name="password" placeholder="Password" required>
<input type="hidden" name="token" value="{token}">
<button type="submit">Connect</button></form>
<p><small>Your password is used only to mint Garmin access tokens and is never
stored.</small></p></body></html>"""


def mfa_form(mfa_session_id: str, token: str, error: str = "") -> str:
    mfa_session_id = html.escape(mfa_session_id, quote=True)
    token = html.escape(token, quote=True)
    err = f'<p class="err">{html.escape(error)}</p>' if error else ""
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Enter security code</title><style>{_STYLE}</style></head>
<body><h2>Enter security code</h2>
<p>Garmin sent a verification code to your phone or email.</p>{err}
<form method="post" action="/setup/mfa">
<input type="text" name="mfa_code" placeholder="6-digit code" inputmode="numeric"
       autocomplete="one-time-code" required autofocus>
<input type="hidden" name="mfa_session_id" value="{mfa_session_id}">
<input type="hidden" name="token" value="{token}">
<button type="submit">Verify</button></form></body></html>"""


def done_page() -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>Connected</title><style>{_STYLE}</style></head>
<body><h2>✅ Connected</h2>
<p>Garmin tokens saved. The widget can now load your courses.</p></body></html>"""
