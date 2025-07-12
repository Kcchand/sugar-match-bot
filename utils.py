# utils.py
import aiohttp

async def geocode_address(address):
    """Convert 'city, country' → (lat, lon) via OpenStreetMap."""
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": address, "format": "json", "limit": 1}
    headers = {"User-Agent": "SugarMatchBot/1.0"}

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers) as resp:
                data = await resp.json()
                if data:
                    return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as e:
        print("Geocoding failed:", e)
    return None, None

# ────────── Dial code helper ──────────
COUNTRY_DIAL_PREFIX = {
    "Afghanistan": "+93",  "Albania": "+355", "Algeria": "+213",
    "Argentina": "+54",    "Australia": "+61", "Austria": "+43",
    "Bangladesh": "+880",  "Belgium": "+32",  "Brazil": "+55",
    "Canada": "+1",        "China": "+86",    "France": "+33",
    "Germany": "+49",      "India": "+91",    "Indonesia": "+62",
    "Italy": "+39",        "Japan": "+81",    "Mexico": "+52",
    "Nepal": "+977",       "Netherlands": "+31", "Nigeria": "+234",
    "Pakistan": "+92",     "Russia": "+7",    "Spain": "+34",
    "Sweden": "+46",       "United Kingdom": "+44", "United States": "+1",
    # …add more as needed
}

def dial_prefix_from_address(address: str) -> str | None:
    if "," in address:
        country = address.split(",")[-1].strip()
        return COUNTRY_DIAL_PREFIX.get(country)
    return None
