import argparse
import json
import math
import sys
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

STOCKHOLM = ZoneInfo("Europe/Stockholm")
DAYS = ("Måndag", "Tisdag", "Onsdag", "Torsdag", "Fredag", "Lördag", "Söndag")
MONTHS = ("januari", "februari", "mars", "april", "maj", "juni",
          "juli", "augusti", "september", "oktober", "november", "december")
WEATHER_URL = (
    "https://opendata-download-metfcst.smhi.se/api/category/snow1g/"
    "version/1/geotype/point/lon/13.14/lat/55.67/data.json"
)
FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")


def get_weather():
    with urlopen(WEATHER_URL, timeout=10) as response:
        forecast = json.load(response)
    now = datetime.now(timezone.utc)
    closest = min(
        forecast["timeSeries"],
        key=lambda entry: abs(datetime.fromisoformat(entry["time"]) - now),
    )
    return closest["data"]


def number(data, name, minimum, maximum):
    value = data.get(name)
    if isinstance(value, (float, int)) and minimum <= value <= maximum:
        return value
    return None


def weather_kind(symbol):
    if symbol == 1:
        return "Klart", "sun"
    if symbol in (2, 3):
        return "Halvklart" if symbol == 3 else "Nästan klart", "partly"
    if symbol in (4, 5, 6):
        return {4: "Molnigt", 5: "Mycket molnigt", 6: "Mulet"}[symbol], "cloud"
    if symbol == 7:
        return "Dimma", "fog"
    if symbol in (8, 9, 10, 18, 19, 20):
        return "Regnskurar" if symbol < 18 else "Regn", "rain"
    if symbol in (11, 21):
        return "Åska", "thunder"
    if symbol in (12, 13, 14, 22, 23, 24):
        return "Snöblandat regn", "sleet"
    if symbol in (15, 16, 17, 25, 26, 27):
        return "Snö", "snow"
    return "Prognos", None


def draw_weather_icon(draw, x, y, kind):
    def sun(cx, cy):
        draw.ellipse((cx - 10, cy - 10, cx + 10, cy + 10), outline=0, width=3)
        for i in range(8):
            angle = i * math.pi / 4
            dx, dy = math.cos(angle), math.sin(angle)
            draw.line((cx + 15 * dx, cy + 15 * dy,
                       cx + 20 * dx, cy + 20 * dy), fill=0, width=3)

    if kind == "sun":
        sun(x + 34, y + 26)
        return
    if kind == "partly":
        sun(x + 21, y + 20)
    if kind is None:
        return

    for box in ((8, 23, 36, 46), (20, 10, 50, 46), (39, 23, 62, 46)):
        left, top, right, bottom = box
        draw.ellipse((x + left, y + top, x + right, y + bottom), fill=0)
    draw.rectangle((x + 21, y + 33, x + 50, y + 46), fill=0)

    if kind in ("rain", "sleet"):
        for dx in (20, 32, 44):
            draw.line((x + dx, y + 51, x + dx - 4, y + 59), fill=0, width=3)
    elif kind == "snow":
        for dx in (18, 30, 42):
            draw.ellipse((x + dx, y + 52, x + dx + 4, y + 56), fill=0)
    elif kind == "fog":
        for dy in (51, 57):
            draw.line((x + 13, y + dy, x + 56, y + dy), fill=0, width=2)
    elif kind == "thunder":
        draw.polygon([(x + dx, y + dy) for dx, dy in
                      ((34, 43), (44, 43), (37, 51), (45, 51), (29, 65), (33, 54), (27, 54))], fill=0)


@lru_cache
def font(size, bold):
    filename = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(str(FONT_DIR / filename), size)


def render(weather, trains, activities, updated, calendar_error=False):
    black = Image.new("1", (800, 480), 255)
    red = Image.new("1", black.size, 255)
    ink, accent = ImageDraw.Draw(black), ImageDraw.Draw(red)

    def text(x, y, value, size, *, bold=False, warning=False, width=None, right=False):
        face = font(size, bold)
        if width is not None and face.getlength(value) > width:
            while value and face.getlength(value.rstrip() + "…") > width:
                value = value[:-1]
            value = value.rstrip() + "…"
        (accent if warning else ink).text(
            (x, y), value, font=face, fill=0, anchor="rt" if right else "lt"
        )

    def line(x1, y1, x2, y2):
        ink.line((x1, y1, x2, y2), fill=0, width=1)

    date = f"{DAYS[updated.weekday()]} {updated.day} {MONTHS[updated.month - 1]}"
    text(24, 20, date, 31, bold=True)
    text(776, 29, f"Senast uppdaterad {updated:%H:%M}", 17, right=True)
    line(24, 66, 776, 66)
    line(300, 87, 300, 425)

    text(24, 85, "Hjärup → Malmö C", 24, bold=True)
    text(24, 121, "Kommande avgångar", 16)
    for index, (label, delayed) in enumerate(trains[:2]):
        size = 38 if len(label) <= 5 else 29 if delayed else 18
        text(24, 151 + index * 49, label, size, bold=True, warning=delayed, width=252)

    line(24, 246, 276, 246)
    text(24, 262, "Väder i Hjärup", 22, bold=True)
    if weather is None:
        text(24, 301, "Prognos saknas", 19)
    else:
        temperature = number(weather, "air_temperature", -70, 70)
        temperature_label = "—" if temperature is None else f"{round(temperature):+d}".replace("+0", "0")
        text(24, 295, f"{temperature_label} °C", 45, bold=True)
        label, kind = weather_kind(weather.get("symbol_code"))
        draw_weather_icon(ink, 199, 289, kind)
        text(24, 350, label, 18, bold=True, width=252)

        speed = number(weather, "wind_speed", 0, 100)
        direction = number(weather, "wind_from_direction", 0, 360)
        gust = number(weather, "wind_speed_of_gust", 0, 150)
        risk = number(weather, "probability_of_precipitation", 0, 100)

        if speed is not None:
            compass = ("N", "NO", "O", "SO", "S", "SV", "V", "NV")
            bearing = compass[int((direction + 22.5) // 45) % 8] if direction is not None else ""
            wind = f"Vind {bearing + ' ' if bearing else ''}{speed:.0f} m/s"
            if gust is not None:
                wind += f" · byar {gust:.0f}"
            text(24, 376, wind, 16, width=252)
        if risk is not None:
            text(24, 401, f"Nederbördsrisk {risk:.0f} %", 16)

    for name, top in (("Sam", 84), ("Li", 257)):
        text(324, top, name, 27, bold=True)
        events = activities.get(name, [])
        if not events:
            message = "Kalendern kunde inte hämtas" if calendar_error else "Inga kommande aktiviteter"
            text(324, top + 39, message, 17)

        for index, (title, place, times) in enumerate(events[:2]):
            row = top + 35 + index * 65
            text(324, row, title, 18, bold=True, width=452)
            text(324, row + 22, place, 17, width=452)
            text(324, row + 43, times, 17, width=452)

    line(324, 249, 776, 249)
    line(24, 439, 776, 439)
    text(24, 452, "Tågdata från Trafiklab.se  ·  Väderprognos från SMHI  ·  Kalender från SportAdmin", 14)
    return black, red


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", type=Path, help="Spara en PNG med exempeldata")
    args = parser.parse_args()

    if args.preview:
        weather = {"air_temperature": 1, "symbol_code": 9, "wind_speed": 5,
                   "wind_from_direction": 225, "wind_speed_of_gust": 9,
                   "probability_of_precipitation": 70}
        trains = [("13:54", False), ("14:09 → 14:14", True)]
        activities = {
            "Sam": [
                ("Mån 23/11 · Träning · PX-lag", "Idrottshallen Hjärup", "Samling 19:15 · 19:30–21:00"),
                ("Ons 25/11 · Träning · P12/13", "Bråhögshallen", "Samling 18:45 · 19:15–20:30"),
            ],
            "Li": [
                ("Mån 23/11 · Träning · F17/18", "Bråhögshallen", "Samling 17:45 · 17:45–19:00"),
                ("Tis 24/11 · Träning · F2018 Hjärup", "Hjärupslundshallen", "Samling 17:30 · 17:30–18:45"),
            ],
        }
        date = datetime(2026, 11, 23, 13, 48, tzinfo=STOCKHOLM)
        black, red = render(weather, trains, activities, date)
        image = black.convert("RGB")
        image.paste((177, 27, 27), (0, 0, *image.size), red.point(lambda pixel: 255 - pixel))
        image.save(args.preview)
        return

    from hallskarm_kalender import next_activities
    from hallskarm_tag import next_trains

    try:
        weather = get_weather()
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"SMHI: {type(error).__name__}", flush=True)
        weather = None

    trains = next_trains()
    calendar_error = False
    try:
        activities = next_activities()
    except (OSError, ValueError) as error:
        print(f"SportAdmin: {type(error).__name__}", flush=True)
        activities = {}
        calendar_error = True

    black, red = render(weather, trains, activities, datetime.now(STOCKHOLM), calendar_error)

    driver_dir = Path.home() / "e-Paper/RaspberryPi_JetsonNano/python/lib"
    sys.path.insert(0, str(driver_dir))
    from waveshare_epd import epd7in5b_V2

    epd = epd7in5b_V2.EPD()
    epd.init()
    try:
        print("Uppdaterar hallskärmen...", flush=True)
        epd.display(epd.getbuffer(black), epd.getbuffer(red))
    finally:
        epd.sleep()
    print("Hallskärmen är klar.")


if __name__ == "__main__":
    main()
