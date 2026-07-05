"""
Self-contained login CAPTCHA (کد امنیتی) — no external/paid service.

Stateless design: the server draws a short random code into an SVG image and
hands the browser back the image plus a short-lived signed token. The token
carries only a salted HASH of the code (never the plaintext), so a client
that inspects the token still can't read the answer — it can only be read off
the rendered image, which is the whole point.

On login the browser returns the token together with whatever the user typed;
the server re-hashes the typed answer and compares. No session store, no DB
row, nothing to clean up — the 5-minute expiry in the signed token is the
only state.

Ambiguous characters (0/O, 1/I/L) are excluded so the image is readable.
"""

import hashlib
import random
import secrets
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from auth import ALGORITHM, SECRET_KEY

_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O/1/I/L
_LEN = 5
_TTL_SECONDS = 300
_PURPOSE = "captcha"


def _hash(code: str) -> str:
    return hashlib.sha256(f"{code.upper()}:{SECRET_KEY}".encode()).hexdigest()


def _svg(code: str) -> str:
    """A small noisy SVG rendering of the code. Self-contained (no fonts/
    images), safe to inline — every value here is server-generated."""
    w, h = 168, 56
    rng = random.Random(secrets.randbits(64))
    colors = ["#2563eb", "#0f766e", "#7c3aed", "#b91c1c", "#a16207", "#152238"]
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">']
    parts.append(f'<rect width="{w}" height="{h}" rx="8" fill="#f1f3f8"/>')
    # a few faint noise lines
    for _ in range(4):
        x1, y1, x2, y2 = rng.randint(0, w), rng.randint(0, h), rng.randint(0, w), rng.randint(0, h)
        parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#c7cede" stroke-width="1"/>')
    step = (w - 24) / _LEN
    for i, ch in enumerate(code):
        x = 16 + i * step
        y = rng.randint(34, 40)
        rot = rng.randint(-24, 24)
        color = rng.choice(colors)
        parts.append(
            f'<text x="{x:.0f}" y="{y}" font-family="Segoe UI,Arial,sans-serif" '
            f'font-size="30" font-weight="700" fill="{color}" '
            f'transform="rotate({rot} {x:.0f} {y})">{ch}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


def generate_captcha() -> dict:
    """Return a fresh challenge: {captcha_token, image} where image is a
    data: URI the browser can drop straight into an <img src>."""
    code = "".join(secrets.choice(_ALPHABET) for _ in range(_LEN))
    expire = datetime.now(timezone.utc) + timedelta(seconds=_TTL_SECONDS)
    token = jwt.encode(
        {"h": _hash(code), "exp": expire, "purpose": _PURPOSE},
        SECRET_KEY, algorithm=ALGORITHM,
    )
    svg = _svg(code)
    import base64
    data_uri = "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()
    return {"captcha_token": token, "image": data_uri}


def verify_captcha(token: str, answer: str) -> bool:
    if not token or not answer:
        return False
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return False
    if payload.get("purpose") != _PURPOSE:
        return False
    expected = payload.get("h")
    if not expected:
        return False
    # constant-time compare of the salted hashes
    return secrets.compare_digest(expected, _hash(answer.strip()))
