import json
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

API_URL = "https://realtime-api.trafiklab.se/v1/departures/740000942"
DESTINATIONS = {
    "trelleborg",
    "simrishamn",
    "malmö c",
    "malmö central",
    "malmö centralstation",
}


def next_trains():
    now = datetime.now()
    trains = {}

    try:
        key = (Path.home() / ".hallskarm-trafiklab").read_text().strip()
        if not key:
            raise ValueError("Trafiklab-nyckeln saknas")

        # Trafiklab returnerar en timme per anrop.
        for hours_ahead in range(3):
            start = now + timedelta(hours=hours_ahead)
            query = urlencode({"key": key})
            url = f"{API_URL}/{start:%Y-%m-%dT%H:%M}?{query}"

            with urlopen(url, timeout=10) as response:
                departures = json.load(response)["departures"]

            for departure in departures:
                route = departure["route"]
                direction = (route.get("direction") or "").casefold().strip()
                if route["transport_mode"] != "TRAIN" or departure.get("canceled"):
                    continue
                if direction not in DESTINATIONS:
                    continue

                scheduled = datetime.fromisoformat(departure["scheduled"])
                expected = datetime.fromisoformat(
                    departure.get("realtime") or departure["scheduled"]
                )
                if expected >= now:
                    trains[scheduled, direction] = expected

            if len(trains) >= 2:
                break

    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Trafiklab: {error}", flush=True)
        return [("Tågdata saknas", False)]

    result = []
    ordered = sorted(trains.items(), key=lambda item: item[1])

    for (scheduled, direction), expected in ordered[:2]:
        scheduled_text = f"{scheduled:%H:%M}"
        expected_text = f"{expected:%H:%M}"
        label = expected_text
        if expected > scheduled and expected_text != scheduled_text:
            label = f"{scheduled_text} → {expected_text}"
        result.append((label, label != expected_text))

    return result or [("Inga tåg inom 3 timmar", False)]


if __name__ == "__main__":
    for label, _ in next_trains():
        print(label)
