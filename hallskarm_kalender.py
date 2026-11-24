import re
from datetime import datetime, timezone
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


def select_activities(feed, now):
    if "BEGIN:VCALENDAR" not in feed:
        raise ValueError("SportAdmin gav inget kalenderflöde")

    feed = re.sub(r"\r?\n[ \t]", "", feed)
    activities = {name: {} for name in GROUPS}

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
            continue

        start_value = fields.get("DTSTART", "")
        end_value = fields.get("DTEND", "")
        if "T" not in start_value:
            continue
        try:
            start = calendar_time(start_value)
            end = calendar_time(end_value) if "T" in end_value else None
        except ValueError:
            continue

        previous = activities[name].get(kind)
        if start < now or (previous and previous[0] <= start):
            continue

        description = calendar_text(fields.get("DESCRIPTION", ""))
        meeting = re.search(r"(?im)^Samling:\s*(\d{1,2}:\d{2})", description)
        meeting_text = meeting[1] if meeting else "—"
        end_text = f"{end:%H:%M}" if end else "—"
        date = f"{DAYS[start.weekday()]} {start.day}/{start.month}"
        location = calendar_text(fields.get("LOCATION", "")).strip() or "Plats saknas"

        activities[name][kind] = (
            start,
            f"{date} · {title}",
            location,
            f"Samling {meeting_text} · {start:%H:%M}–{end_text}",
        )

    return {
        name: [events[kind][1:] for kind in ("training", "match") if kind in events]
        for name, events in activities.items()
    }


def next_activities():
    url = (Path.home() / ".hallskarm-sportadmin").read_text().strip()
    if url.startswith("webcal://"):
        url = "https://" + url.removeprefix("webcal://")
    with urlopen(url, timeout=12) as response:
        feed = response.read().decode("utf-8-sig")
    return select_activities(feed, datetime.now(STOCKHOLM))


if __name__ == "__main__":
    for name, events in next_activities().items():
        print(name)
        for event in events:
            print(" | ".join(event))
