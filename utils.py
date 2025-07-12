# utils.py

import aiohttp

async def geocode_address(address):
    """Returns (lat, lon) from 'City, Country' using OpenStreetMap Nominatim"""
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": address,
        "format": "json",
        "limit": 1
    }
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
