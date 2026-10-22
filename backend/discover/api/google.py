"""Google sign-in: the browser gets an ID token from Google; the API checks it with Google before trusting anything in it."""

from __future__ import annotations

import httpx

TOKENINFO = "https://oauth2.googleapis.com/tokeninfo"
ISSUERS = ("accounts.google.com", "https://accounts.google.com")


class GoogleAuthError(Exception):
    pass


async def verify_google(credential: str, client_id: str, transport: httpx.AsyncBaseTransport | None = None) -> dict[str, str]:
    """Returns {"email", "name"} for a valid ID token issued to OUR client id with a verified email; raises GoogleAuthError otherwise.
    Google validates the signature and expiry; we check the audience, the issuer and the verified flag."""
    if not client_id:
        raise GoogleAuthError("Google sign-in is not set up")
    try:
        async with httpx.AsyncClient(timeout=10, transport=transport) as c:
            r = await c.get(TOKENINFO, params={"id_token": credential})
    except httpx.HTTPError as exc:
        raise GoogleAuthError("Could not reach Google") from exc
    if r.status_code != 200:
        raise GoogleAuthError("Google did not accept this sign-in")
    d = r.json()
    if d.get("aud") != client_id or d.get("iss") not in ISSUERS:
        raise GoogleAuthError("This sign-in was not issued for this app")
    if str(d.get("email_verified")).lower() != "true" or not d.get("email"):
        raise GoogleAuthError("Your Google email is not verified")
    return {"email": str(d["email"]).lower(), "name": str(d.get("name") or "")[:120]}
