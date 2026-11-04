import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import requests

from tools import weather

# 2026-11-04 19:06 UTC = 20:06 in Berlin (UTC+1)
NOW = datetime(2026, 11, 4, 19, 6, tzinfo=timezone.utc)

GEO = {"results": [{
    "name": "Berlin", "admin1": "State of Berlin", "country": "Germany",
    "latitude": 52.52437, "longitude": 13.41053, "timezone": "Europe/Berlin",
}]}


def _forecast(current_time="2026-11-04T20:00", with_current=True):
    data = {
        "timezone": "Europe/Berlin",
        "utc_offset_seconds": 3600,
        "current_units": {"temperature_2m": "°C", "wind_speed_10m": "km/h"},
        "daily": {
            "time": ["2026-11-04"],
            "temperature_2m_max": [9.9], "temperature_2m_min": [5.5],
            "precipitation_probability_max": [0], "weather_code": [3],
        },
        "hourly": {
            "time": ["2026-11-04T20:00", "2026-11-04T23:00", "2026-11-05T03:00", "2026-11-05T07:00"],
            "temperature_2m": [8.3, 7.7, 6.0, 4.7],
            "precipitation_probability": [0, 5, 10, 0],
            "weather_code": [2, 2, 3, 3],
        },
    }
    if with_current:
        data["current"] = {
            "time": current_time, "interval": 900,
            "temperature_2m": 8.3, "apparent_temperature": 5.9, "relative_humidity_2m": 72,
            "precipitation": 0.0, "weather_code": 2, "wind_speed_10m": 6.3, "is_day": 0,
        }
    return data


def _resp(payload, status=200):
    r = MagicMock(status_code=status)
    r.json.return_value = payload
    if status >= 400:
        r.raise_for_status.side_effect = requests.HTTPError(f"{status} error")
    return r


def _get_router(geo=GEO, forecast=None, forecast_exc=None):
    def fake_get(url, params=None, timeout=None):
        if "geocoding" in url:
            return _resp(geo)
        if forecast_exc:
            raise forecast_exc
        return _resp(forecast if forecast is not None else _forecast())
    return fake_get


def setup_function():
    weather._GEO_CACHE.clear()


def test_fresh_current_conditions_include_timestamp_units_location_and_source():
    with patch("tools.weather.requests.get", side_effect=_get_router()):
        out = weather.get_weather("Berlin", now=NOW)

    assert "Berlin, State of Berlin, Germany" in out
    assert "2026-11-04 20:00" in out            # observation time, local
    assert "8.3°C" in out and "46.9°F" in out    # current temp, both units
    assert "feels like 5.9°C" in out
    assert "partly cloudy" in out
    assert "Open-Meteo" in out
    assert "STALE" not in out


def test_today_and_next_hours_come_from_forecast_data_not_climate():
    with patch("tools.weather.requests.get", side_effect=_get_router()):
        out = weather.get_weather("Berlin", now=NOW)

    assert "high 9.9°C" in out and "low 5.5°C" in out
    # "tonight" must be grounded in the hourly forecast: lowest 4.7 at 07:00
    assert "4.7°C" in out and "07:00" in out
    # nothing seasonal/monthly is offered for the model to extrapolate from
    assert "average" not in out.lower() and "november" not in out.lower()


def test_stale_reading_is_flagged_so_it_is_not_reported_as_current():
    old = _forecast(current_time="2026-11-04T14:00")  # 6 hours before NOW
    with patch("tools.weather.requests.get", side_effect=_get_router(forecast=old)):
        out = weather.get_weather("Berlin", now=NOW)

    assert "STALE" in out
    assert "do not present" in out.lower()


def test_location_not_found():
    with patch("tools.weather.requests.get", side_effect=_get_router(geo={})):
        out = weather.get_weather("Atlantisville", now=NOW)

    assert out.startswith("LOCATION NOT FOUND")
    assert "Atlantisville" in out


def test_service_timeout_returns_unavailable_without_numbers():
    with patch("tools.weather.requests.get", side_effect=_get_router(forecast_exc=requests.Timeout())):
        out = weather.get_weather("Berlin", now=NOW)

    assert out.startswith("WEATHER UNAVAILABLE")
    assert "do not guess" in out.lower()
    assert "°" not in out


def test_missing_current_block_returns_unavailable():
    with patch("tools.weather.requests.get", side_effect=_get_router(forecast=_forecast(with_current=False))):
        out = weather.get_weather("Berlin", now=NOW)

    assert out.startswith("WEATHER UNAVAILABLE")


def test_http_error_returns_unavailable():
    def fake_get(url, params=None, timeout=None):
        if "geocoding" in url:
            return _resp(GEO)
        return _resp({}, status=503)
    with patch("tools.weather.requests.get", side_effect=fake_get):
        out = weather.get_weather("Berlin", now=NOW)

    assert out.startswith("WEATHER UNAVAILABLE")


def test_country_code_is_passed_to_geocoding():
    calls = []
    router = _get_router()

    def spy(url, params=None, timeout=None):
        calls.append((url, params))
        return router(url, params, timeout)

    with patch("tools.weather.requests.get", side_effect=spy):
        weather.get_weather("Berlin", country_code="de", now=NOW)

    geo_params = next(p for u, p in calls if "geocoding" in u)
    assert geo_params["countryCode"] == "DE"


def test_geocoding_result_is_cached_between_calls():
    calls = []
    router = _get_router()

    def spy(url, params=None, timeout=None):
        calls.append(url)
        return router(url, params, timeout)

    with patch("tools.weather.requests.get", side_effect=spy):
        weather.get_weather("Berlin", now=NOW)
        weather.get_weather("berlin", now=NOW)

    assert sum("geocoding" in u for u in calls) == 1


def test_agent_offers_get_weather_and_dispatches_it():
    import agent
    assert "get_weather" in {t["name"] for t in agent.TOOLS}
    with patch("agent.get_weather", return_value="WEATHER DATA ...") as mock_weather:
        out = agent._execute_tool("get_weather", {"location": "Berlin", "country_code": "DE"}, MagicMock())
    mock_weather.assert_called_once_with("Berlin", country_code="DE")
    assert out == "WEATHER DATA ..."


def test_system_prompt_forbids_ungrounded_and_seasonal_answers():
    import agent
    prompt = agent._SYSTEM_PROMPT.lower()
    assert "get_weather" in prompt
    assert "seasonal" in prompt and "never" in prompt
