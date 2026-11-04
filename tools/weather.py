"""Current weather from Open-Meteo (https://open-meteo.com): free, no API key, plain JSON.

Web search is unreliable for "what's the weather": results mix live readings with
monthly climate pages, and the model then extrapolates seasonal ranges. This tool
returns one structured, timestamped reading plus the forecast for today and the
next 12 hours, and says plainly when data is stale or unavailable.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = 2.5            # seconds per call; Alexa allows ~8s for the whole turn
STALE_AFTER = timedelta(hours=3)
SOURCE = "Open-Meteo (model-based current conditions, updated every 15 minutes)"

# WMO weather interpretation codes, as used by Open-Meteo.
WMO = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "freezing fog",
    51: "light drizzle", 53: "moderate drizzle", 55: "dense drizzle",
    56: "light freezing drizzle", 57: "dense freezing drizzle",
    61: "light rain", 63: "moderate rain", 65: "heavy rain",
    66: "light freezing rain", 67: "heavy freezing rain",
    71: "light snow", 73: "moderate snow", 75: "heavy snow", 77: "snow grains",
    80: "light rain showers", 81: "moderate rain showers", 82: "violent rain showers",
    85: "light snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm with light hail", 99: "thunderstorm with heavy hail",
}

_GEO_CACHE: Dict[Tuple[str, str], dict] = {}  # survives warm Lambda invocations


def _unavailable(reason: str) -> str:
    return (
        f"WEATHER UNAVAILABLE: {reason}. Do not guess, and do not use seasonal, typical "
        "or monthly values; tell the user the current weather couldn't be retrieved."
    )


def _c(value: float) -> str:
    return f"{value:.1f}°C ({value * 9 / 5 + 32:.1f}°F)"


def _describe(code) -> str:
    return WMO.get(code, f"weather code {code}")


def _geocode(location: str, country_code: Optional[str]) -> Optional[dict]:
    key = (location.strip().lower(), (country_code or "").upper())
    if key in _GEO_CACHE:
        return _GEO_CACHE[key]
    params = {"name": location.strip(), "count": 1, "language": "en", "format": "json"}
    if country_code:
        params["countryCode"] = country_code.upper()
    resp = requests.get(GEOCODE_URL, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    results = resp.json().get("results") or []
    place = results[0] if results else None
    if place:
        _GEO_CACHE[key] = place
    return place


def _next_hours(hourly: dict) -> Optional[str]:
    times = hourly.get("time") or []
    temps = hourly.get("temperature_2m") or []
    if not times or len(temps) != len(times):
        return None
    lo = min(range(len(temps)), key=lambda i: temps[i])
    hi = max(range(len(temps)), key=lambda i: temps[i])
    precip = [p for p in (hourly.get("precipitation_probability") or []) if p is not None]
    codes = []
    for c in hourly.get("weather_code") or []:
        if _describe(c) not in codes:
            codes.append(_describe(c))

    def when(t: str) -> str:
        day, hour = t.split("T")
        return f"{hour} on {day}"

    parts = [
        f"Next {len(times)} hours ({when(times[0])} to {when(times[-1])}): "
        f"lowest {_c(temps[lo])} at {when(times[lo])}, highest {_c(temps[hi])} at {when(times[hi])}"
    ]
    if precip:
        parts.append(f"max precipitation chance {max(precip)}%")
    if codes:
        parts.append("conditions " + ", ".join(codes))
    return "; ".join(parts) + "."


def get_weather(location: str, country_code: Optional[str] = None, now: Optional[datetime] = None) -> str:
    """Return current conditions plus today's and the next 12 hours' forecast as text."""
    now = now or datetime.now(timezone.utc)
    try:
        place = _geocode(location, country_code)
    except Exception as e:
        logger.warning("Geocoding failed for %r: %s", location, e)
        return _unavailable("the location lookup service did not respond")
    if not place:
        return (
            f"LOCATION NOT FOUND: no place named '{location}'. Ask the user which city they mean; "
            "do not guess the weather."
        )

    try:
        resp = requests.get(FORECAST_URL, params={
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "timezone": "auto",
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,"
                       "precipitation,weather_code,wind_speed_10m,is_day",
            "hourly": "temperature_2m,precipitation_probability,weather_code",
            "forecast_hours": 12,
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code",
            "forecast_days": 1,
        }, timeout=TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        cur = data["current"]
        observed_local = datetime.strptime(cur["time"], "%Y-%m-%dT%H:%M")
        observed_utc = (observed_local - timedelta(seconds=data.get("utc_offset_seconds", 0))).replace(tzinfo=timezone.utc)
        temp = cur["temperature_2m"]
    except Exception as e:
        logger.warning("Weather fetch failed for %r: %s", location, e)
        return _unavailable("the weather service did not return current conditions")

    name = ", ".join(p for p in (place.get("name"), place.get("admin1"), place.get("country")) if p)
    age = now - observed_utc
    age_min = max(0, int(age.total_seconds() // 60))
    lines = [
        f"WEATHER DATA from {SOURCE}.",
        f"Location: {name} ({place['latitude']:.2f}, {place['longitude']:.2f}), timezone {data.get('timezone')}.",
    ]
    if age > STALE_AFTER:
        lines.append(
            f"WARNING: this reading is STALE ({age.total_seconds() / 3600:.1f} hours old). Do not present it "
            f"as current conditions; say the latest available reading is from {cur['time'].replace('T', ' ')} local time."
        )
    current = (
        f"Current conditions as of {cur['time'].replace('T', ' ')} local time ({age_min} minutes ago): "
        f"{_c(temp)}"
    )
    if cur.get("apparent_temperature") is not None:
        current += f", feels like {_c(cur['apparent_temperature'])}"
    current += f", {_describe(cur.get('weather_code'))}"
    if cur.get("relative_humidity_2m") is not None:
        current += f", humidity {cur['relative_humidity_2m']}%"
    if cur.get("wind_speed_10m") is not None:
        kmh = cur["wind_speed_10m"]
        current += f", wind {kmh:.0f} km/h ({kmh * 0.621371:.0f} mph)"
    if cur.get("precipitation") is not None:
        current += f", precipitation in the last 15 minutes {cur['precipitation']} mm"
    lines.append(current + ".")

    daily = data.get("daily") or {}
    try:
        lines.append(
            f"Today ({daily['time'][0]}): high {_c(daily['temperature_2m_max'][0])}, "
            f"low {_c(daily['temperature_2m_min'][0])}, "
            f"max precipitation chance {daily['precipitation_probability_max'][0]}%, "
            f"{_describe(daily['weather_code'][0])}."
        )
    except (KeyError, IndexError, TypeError):
        pass

    upcoming = _next_hours(data.get("hourly") or {})
    if upcoming:
        lines.append(upcoming)
    lines.append("Report only values listed here.")
    return "\n".join(lines)
