"""Live data integration (the Tier-2 'live + safety' layer).

BOM blocks automated access (HTTP 403 — they don't permit scraping; organisations
use registered BOM data feeds via agreement). So for an open, automated-access
source we use Open-Meteo (free, no key, reliable) for current conditions and the
rain forecast, and derive an indicative wet-season flood-risk signal from rainfall.

This is the data an MCP `live_weather` / `flood_risk` tool serves to the agent.
Honesty: the flood-risk level here is INDICATIVE (rainfall-based), not an official
BOM flood warning. A production council deployment would swap in registered BOM
feeds behind the same tool interface.
"""
from __future__ import annotations

from .http import get_json  # reuse the dependency-free HTTP helper

DARWIN_LAT, DARWIN_LNG = -12.4634, 130.8456
OPEN_METEO = "https://api.open-meteo.com/v1/forecast"

WEATHER_CODES = {
    0: "clear", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "rime fog", 51: "light drizzle", 53: "drizzle",
    55: "heavy drizzle", 61: "light rain", 63: "rain", 65: "heavy rain",
    80: "rain showers", 81: "heavy showers", 82: "violent showers",
    95: "thunderstorm", 96: "thunderstorm w/ hail", 99: "severe thunderstorm",
}


def get_weather(lat: float = DARWIN_LAT, lng: float = DARWIN_LNG) -> dict:
    """Current conditions + 5-day rain forecast for Darwin (Open-Meteo)."""
    data = get_json(OPEN_METEO, params={
        "latitude": lat, "longitude": lng,
        "current": "temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m",
        "daily": "precipitation_sum,precipitation_probability_max,weather_code",
        "timezone": "Australia/Darwin", "forecast_days": 5,
    })
    cur = data.get("current", {})
    daily = data.get("daily", {})
    forecast = []
    for i, date in enumerate(daily.get("time", [])):
        forecast.append({
            "date": date,
            "rain_mm": daily["precipitation_sum"][i],
            "rain_chance_pct": daily["precipitation_probability_max"][i],
            "conditions": WEATHER_CODES.get(daily["weather_code"][i], "unknown"),
        })
    return {
        "location": "Darwin, NT",
        "observed_now": {
            "temp_c": cur.get("temperature_2m"),
            "humidity_pct": cur.get("relative_humidity_2m"),
            "rain_mm": cur.get("precipitation"),
            "wind_kmh": cur.get("wind_speed_10m"),
            "conditions": WEATHER_CODES.get(cur.get("weather_code"), "unknown"),
        },
        "forecast": forecast,
        "source": "Open-Meteo (open API). Not an official BOM forecast.",
    }


def flood_risk(lat: float = DARWIN_LAT, lng: float = DARWIN_LNG) -> dict:
    """Indicative wet-season flood-risk signal derived from rain forecast.

    Thresholds are deliberately simple and transparent (mm of forecast rain).
    INDICATIVE ONLY — not an official BOM flood warning.
    """
    w = get_weather(lat, lng)
    next3 = w["forecast"][:3]
    max_day = max((d["rain_mm"] or 0) for d in next3) if next3 else 0
    total3 = sum((d["rain_mm"] or 0) for d in next3)
    if max_day >= 100 or total3 >= 150:
        level, advice = "HIGH", "Heavy rain forecast. Monitor BOM warnings; avoid low-lying/flood-prone roads."
    elif max_day >= 50 or total3 >= 80:
        level, advice = "ELEVATED", "Significant rain forecast. Stay alert to local flooding in low areas."
    elif max_day >= 15:
        level, advice = "MODERATE", "Some rain forecast. Minor pooling possible."
    else:
        level, advice = "LOW", "Little rain forecast. No rainfall-based flood concern."
    return {
        "location": "Darwin, NT",
        "flood_risk_level": level,
        "advice": advice,
        "max_daily_rain_mm_next3": round(max_day, 1),
        "total_rain_mm_next3": round(total3, 1),
        "based_on": next3,
        "disclaimer": "INDICATIVE rainfall-based signal only. For official warnings see BOM.",
    }
