import argparse
import json
import math
import sys
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path
from urllib.request import urlopen
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont

from hallskarm_kalender import next_three_days, three_day_activities

STOCKHOLM = ZoneInfo("Europe/Stockholm")
DAYS = ("Måndag", "Tisdag", "Onsdag", "Torsdag", "Fredag", "Lördag", "Söndag")
MONTHS = ("januari", "februari", "mars", "april", "maj", "juni",
          "juli", "augusti", "september", "oktober", "november", "december")
WEATHER_URL = (
    "https://opendata-download-metfcst.smhi.se/api/category/snow1g/"
    "version/1/geotype/point/lon/13.14/lat/55.67/data.json"
)
TEXT_SMALL = 15
TEXT_MEDIUM = 21
TEXT_LARGE = 31
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


def draw_sport_icon(draw, x, y, sport):
    if sport == "handboll":
        draw.ellipse((x + 2, y + 2, x + 16, y + 16), outline=0, width=2)
        draw.arc((x + 5, y + 2, x + 13, y + 16), 85, 270, fill=0)
        draw.line((x + 3, y + 11, x + 15, y + 7), fill=0)
    elif sport == "innebandy":
        draw.line((x + 13, y + 1, x + 8, y + 13, x + 2, y + 13), fill=0, width=3)
        draw.ellipse((x + 12, y + 12, x + 16, y + 16), outline=0)
    elif sport == "gymnastik":
        draw.ellipse((x + 7, y, x + 11, y + 4), fill=0)
        draw.line((x + 2, y + 6, x + 9, y + 9, x + 16, y + 5), fill=0, width=2)
        draw.line((x + 9, y + 6, x + 9, y + 11), fill=0, width=2)
        draw.line((x + 3, y + 16, x + 9, y + 11, x + 15, y + 16), fill=0, width=2)


@lru_cache
def font(size):
    return ImageFont.truetype(str(FONT_DIR / "DejaVuSans-Bold.ttf"), size)


def christmas_countdown(today):
    days_left = (date(today.year, 12, 24) - today).days
    if days_left == 0:
        return "God jul!"
    if days_left == 1:
        return "1 dag till julafton"
    if 2 <= days_left <= 30:
        return f"{days_left} dagar till julafton"
    return None


def draw_santa_hat(ink, accent, x, y):
    accent.polygon([(x + 3, y + 22), (x + 9, y + 8), (x + 20, y + 2),
                    (x + 31, y + 5), (x + 35, y + 13), (x + 26, y + 11),
                    (x + 27, y + 22)], fill=0)
    ink.rounded_rectangle((x + 1, y + 21, x + 29, y + 29),
                          radius=3, outline=0, width=2)
    ink.ellipse((x + 29, y + 12, x + 39, y + 22), outline=0, width=2)


def render(weather, trains, activities, updated, calendar_error=False):
    black = Image.new("1", (800, 480), 255)
    red = Image.new("1", black.size, 255)
    ink, accent = ImageDraw.Draw(black), ImageDraw.Draw(red)

    def text(x, y, value, size, *, warning=False, width=None, right=False):
        face = font(size)
        if width is not None and face.getlength(value) > width:
            while value and face.getlength(value.rstrip() + "…") > width:
                value = value[:-1]
            value = value.rstrip() + "…"
        (accent if warning else ink).text(
            (x, y), value, font=face, fill=0, anchor="rt" if right else "lt"
        )

    date_label = f"{DAYS[updated.weekday()]} {updated.day} {MONTHS[updated.month - 1]}"
    text(24, 20, date_label, TEXT_LARGE)
    countdown = christmas_countdown(updated.date())
    if countdown:
        countdown_x = 776 - round(font(TEXT_MEDIUM).getlength(countdown))
        draw_santa_hat(ink, accent, countdown_x - 49, 15)
        text(776, 21, countdown, TEXT_MEDIUM, right=True)
    text(776, 52 if countdown else 29, f"Senast uppdaterad {updated:%H:%M}",
         TEXT_SMALL, right=True)

    text(24, 85, "Hjärup → Malmö C", TEXT_MEDIUM)
    text(24, 121, "Kommande avgångar", TEXT_SMALL)
    for index, (label, delayed) in enumerate(trains[:2]):
        size = TEXT_LARGE if len(label) <= 5 else TEXT_MEDIUM
        text(24, 151 + index * 49, label, size, warning=delayed, width=252)

    text(24, 262, "Väder i Hjärup", TEXT_MEDIUM)
    if weather is None:
        text(24, 301, "Prognos saknas", TEXT_MEDIUM)
    else:
        temperature = number(weather, "air_temperature", -70, 70)
        temperature_label = "—" if temperature is None else f"{round(temperature):+d}".replace("+0", "0")
        text(24, 299, f"{temperature_label} °C", TEXT_LARGE)
        label, kind = weather_kind(weather.get("symbol_code"))
        draw_weather_icon(ink, 199, 289, kind)
        text(24, 350, label, TEXT_MEDIUM, width=252)

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
            text(24, 376, wind, TEXT_SMALL, width=252)
        if risk is not None:
            text(24, 401, f"Nederbördsrisk {risk:.0f} %", TEXT_SMALL)

    if calendar_error:
        text(324, 122, "Kalendern kunde inte hämtas", TEXT_SMALL)
    else:
        row = 88
        total = sum(map(len, activities.values()))
        # Reserve room for all three headings and a notice on unusually busy days.
        max_events = 6
        row_height = 44 if total <= 4 else 36
        shown = 0
        for day, events in activities.items():
            heading = f"{DAYS[day.weekday()]} {day.day} {MONTHS[day.month - 1]}"
            text(324, row, heading, TEXT_MEDIUM)
            row += 26

            if not events and total <= 4:
                text(324, row, "Inga aktiviteter", TEXT_SMALL)
                row += 21

            for event in events[:max_events - shown]:
                draw_sport_icon(ink, 324, row + 2, event.sport)
                sport = event.sport.capitalize()
                if event.kind == "training" and sport:
                    label = f"{event.name} · {sport}"
                else:
                    label = f"{event.name} · {event.title}"
                text(350, row, label, TEXT_MEDIUM, width=220)
                if event.meeting != "—":
                    text(625, row + 4, f"({event.meeting})", TEXT_SMALL, right=True)
                text(776, row, event.hours, TEXT_MEDIUM, right=True)
                text(350, row + 23, event.place, TEXT_SMALL, width=280)
                row += row_height
                shown += 1

            row += 5

        if shown < total:
            text(324, row, f"+ {total - shown} till i SportAdmin", TEXT_SMALL, width=752)

    text(24, 452, "Tågdata från Trafiklab.se  ·  Väderprognos från SMHI  ·  Kalender från SportAdmin", TEXT_SMALL, width=752)
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
        date = datetime(2026, 11, 24, 11, 0, tzinfo=STOCKHOLM)
        examples = [
            ("20261124", "1730", "1845", "1730", "F2018 Hjärup", "Hjärupslundshallen"),
            ("20261125", "1915", "2030", "1845", "P12/13", "Bråhögshallen"),
            ("20261126", "1800", "1930", "1800", "G18", "Uppåkrahallen"),
            ("20261126", "1915", "2030", "1900", "P13", "Idrottshallen Hjärup"),
        ]
        entries = ["BEGIN:VCALENDAR"]
        for day, start, end, meeting, group, place in examples:
            entries.extend((
                "BEGIN:VEVENT", f"DTSTART:{day}T{start}00", f"DTEND:{day}T{end}00",
                f"SUMMARY:Träning - {group}", f"LOCATION:{place}",
                f"DESCRIPTION:Samling: {meeting[:2]}:{meeting[2:]}", "END:VEVENT",
            ))
        entries.append("END:VCALENDAR")
        activities = three_day_activities("\n".join(entries), date.date())
        black, red = render(weather, trains, activities, date)
        image = black.convert("RGB")
        image.paste((177, 27, 27), (0, 0, *image.size), red.point(lambda pixel: 255 - pixel))
        image.save(args.preview)
        return

    from hallskarm_tag import next_trains

    try:
        weather = get_weather()
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"SMHI: {type(error).__name__}", flush=True)
        weather = None

    trains = next_trains()
    updated = datetime.now(STOCKHOLM)
    calendar_error = False
    try:
        activities = next_three_days(updated.date())
    except (OSError, ValueError) as error:
        print(f"SportAdmin: {type(error).__name__}", flush=True)
        activities = {}
        calendar_error = True

    black, red = render(weather, trains, activities, updated, calendar_error)

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
