"""Normalize TikTok cookie exports for both the GUI and LIVE requests.

The selected Android document can contain a flat browser list, a wrapped
`cookies`/`Cookie` array or a single name/value object.
"""


def normalize_cookie_entries(payload):
    if isinstance(payload, dict):
        if isinstance(payload.get("cookies"), list):
            payload = payload["cookies"]
        elif isinstance(payload.get("Cookie"), list):
            payload = payload["Cookie"]
        elif "name" in payload and "value" in payload:
            payload = [payload]
        else:
            raise RuntimeError("JSON file does not look like a cookies export.")

    if not isinstance(payload, list):
        raise RuntimeError("Cookies JSON must be a list of cookie objects.")

    cookies = []
    for index, cookie in enumerate(payload, 1):
        if not isinstance(cookie, dict):
            raise RuntimeError(f"Cookie entry #{index} is not an object.")

        name = cookie.get("name")
        value = cookie.get("value")
        if name in (None, "") or value is None:
            continue

        entry = dict(cookie)
        entry["name"] = str(name)
        entry["value"] = str(value)

        if "expires" not in entry:
            for key in ("expirationDate", "expiry", "expiration_date"):
                if key in entry:
                    try:
                        entry["expires"] = int(float(entry[key]))
                    except (TypeError, ValueError):
                        pass
                    break

        if "httpOnly" not in entry and "http_only" in entry:
            entry["httpOnly"] = bool(entry.get("http_only"))
        if "sameSite" not in entry and "same_site" in entry:
            entry["sameSite"] = entry.get("same_site")

        cookies.append(entry)

    if not cookies:
        raise RuntimeError("No usable cookies with name/value fields were found.")

    return cookies

