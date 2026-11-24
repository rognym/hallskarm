import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import urlopen
from zoneinfo import ZoneInfo

STOCKHOLM = ZoneInfo("Europe/Stockholm")
DAYS = ("Mån", "Tis", "Ons", "Tor", "Fre", "Lör", "Sön")
GROUPS = {
    "Sam": {"P12/13", "P13", "PX-lag"},
    "Li": {"G18", "F17/18", "F2018 Hjärup"},
}


def calendar_text(value):
    return re.sub(
        r"\\([nN,;\\])",
        lambda match: "\n" if match[1].lower() == "n" else match[1],
        value,
    )


def calendar_time(value):
    if value.endswith("Z"):
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(
            tzinfo=timezone.utc
        ).astimezone(STOCKHOLM)
    return datetime.strptime(value, "%Y%m%dT%H%M%S").replace(tzinfo=STOCKHOLM)


def activity_owner(title):
    group = title.rsplit(" - ", 1)[-1].strip()
    for name, groups in GROUPS.items():
        if group in groups:
            return name

    if title.startswith("Match:"):
        if re.search(r"\bIK Stanstad F17/18\b", title):
            return "Li"
        if re.search(r"\bIK Stanstad P1[23]\b", title):
            return "Sam"
    return None


@dataclass(frozen=True)
class Activity:
    name: str
    title: str
    place: str
    meeting: str
    start: datetime
    end: datetime | None
    kind: str
    sport: str

    @property
    def hours(self):
        end = f"{self.end:%H:%M}" if self.end else "—"
        return f"{self.start:%H:%M}–{end}"


def activity_sport(name, title):
    words = title.casefold()
    group = title.rsplit(" - ", 1)[-1].strip()
    if "handboll" in words or group == "F2018 Hjärup":
        return "handboll"
    if "gymnastik" in words or group == "G18":
        return "gymnastik"
    if "innebandy" in words or name == "Sam" or "IK Stanstad F17/18" in title:
        return "innebandy"
    return ""


def parse_activities(feed):
    if "BEGIN:VCALENDAR" not in feed:
        raise ValueError("SportAdmin gav inget kalenderflöde")

    feed = re.sub(r"\r?\n[ \t]", "", feed)
    for entry in re.findall(r"BEGIN:VEVENT\r?\n(.*?)END:VEVENT", feed, re.S):
        fields = {}
        for line in entry.splitlines():
            key, separator, value = line.partition(":")
            if separator:
                fields[key.split(";", 1)[0]] = value

        title = calendar_text(fields.get("SUMMARY", "")).strip()
        name = activity_owner(title)
        if not name or fields.get("STATUS") == "CANCELLED":
            continue
        sport = activity_sport(name, title)

        if title.startswith("Träning"):
            kind = "training"
            if " - " in title:
                title = "Träning · " + title.rsplit(" - ", 1)[1].strip()
        elif title.startswith("Match:"):
            kind = "match"
            title = title.split(" (Pantamera", 1)[0]
            teams = title.removeprefix("Match: ").split(" - ", 1)
            if len(teams) == 2:
                home, away = teams
                opponent = away if home.startswith("IK Stanstad") else home
                title = f"Match mot {opponent}"
        elif title.startswith("Sammandrag"):
            kind = "match"
            title = "Sammandrag · " + title.rsplit(" - ", 1)[-1].strip()
        else:
            kind = "other"

        start_value = fields.get("DTSTART", "")
        end_value = fields.get("DTEND", "")
        if "T" not in start_value:
            continue
        try:
            start = calendar_time(start_value)
            end = calendar_time(end_value) if "T" in end_value else None
        except ValueError:
            continue

        description = calendar_text(fields.get("DESCRIPTION", ""))
        meeting = re.search(r"(?im)^Samling:\s*(\d{1,2}:\d{2})", description)
        place = calendar_text(fields.get("LOCATION", "")).strip() or "Plats saknas"
        yield Activity(
            name, title, place, meeting[1].zfill(5) if meeting else "—",
            start, end, kind, sport,
        )


def select_activities(feed, now):
    activities = {name: {} for name in GROUPS}
    for event in sorted(parse_activities(feed), key=lambda event: event.start):
        if event.start >= now and event.kind in ("training", "match"):
            activities[event.name].setdefault(event.kind, event)

    return {
        name: [
            (f"{DAYS[event.start.weekday()]} {event.start.day}/{event.start.month} · {event.title}",
             event.place, f"Samling {event.meeting} · {event.hours}")
            for kind in ("training", "match") if (event := events.get(kind))
        ]
        for name, events in activities.items()
    }


def three_day_activities(feed, today):
    days = {today + timedelta(days=offset): [] for offset in range(3)}
    events = defaultdict(set)
    for event in sorted(parse_activities(feed), key=lambda event: event.start):
        day = event.start.date()
        if day in days and event not in events[day]:
            events[day].add(event)
            days[day].append(event)
    return days


def get_calendar_feed():
    url = (Path.home() / ".hallskarm-sportadmin").read_text().strip()
    if url.startswith("webcal://"):
        url = "https://" + url.removeprefix("webcal://")
    with urlopen(url, timeout=12) as response:
        feed = response.read().decode("utf-8-sig")
    return feed


def next_activities():
    return select_activities(get_calendar_feed(), datetime.now(STOCKHOLM))


def next_three_days(today):
    return three_day_activities(get_calendar_feed(), today)


if __name__ == "__main__":
    for day, events in next_three_days(datetime.now(STOCKHOLM).date()).items():
        print(day)
        for event in events:
            print(f"  {event.name} · {event.title} | {event.place} | {event.meeting} | {event.hours}")
