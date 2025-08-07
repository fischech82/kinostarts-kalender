#!/usr/bin/env python3
"""
Script to generate an up‑to‑date iCalendar feed containing upcoming film
release dates for German cinemas.  The script fetches the latest
startdates from InsideKino (https://www.insidekino.com/DStarts/DStartplan.htm),
parses the dates and film titles and writes an iCalendar (.ics) file.

Usage:
    python update_kinostarts_calendar.py [output_file]

If no output file is provided, the script writes to
`kinostarts_calendar.ics` in the current working directory.  Running this
script regularly (for example via cron or a scheduled task) ensures
that the calendar feed stays in sync with the latest data on InsideKino.
"""

import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup


# Mapping of German month names to month numbers.  Used for parsing
# date strings like "7. August 2025".
MONTH_MAP = {
    'Januar': 1,
    'Februar': 2,
    'März': 3,
    'April': 4,
    'Mai': 5,
    'Juni': 6,
    'Juli': 7,
    'August': 8,
    'September': 9,
    'Oktober': 10,
    'November': 11,
    'Dezember': 12,
}


def parse_date(date_str: str) -> datetime:
    """Convert a German date string into a datetime object.

    Date strings on InsideKino can contain additional annotations in
    parentheses (e.g. "14. August 2025 (Mariä Himmelfahrt/Fr)").  This
    function removes everything after the first parenthesis, splits
    the remaining string by whitespace and constructs a `datetime`
    object.

    Args:
        date_str: The raw date string to parse.

    Returns:
        A `datetime` object representing the date.
    """
    # Strip everything after "(" to remove annotations
    date_str = date_str.split('(')[0].strip()
    parts = date_str.split()
    # Expected format: "DD. Month YYYY"
    day = int(parts[0].replace('.', ''))
    month_name = parts[1]
    year = int(parts[2])
    month = MONTH_MAP[month_name]
    return datetime(year, month, day)


def parse_titles(cell) -> list[str]:
    """Extract film titles from a table cell.

    Film titles and distributor codes are separated by `<br>` tags in
    the HTML.  Sometimes the distributor code appears on a separate
    line starting with a parenthesis; this function concatenates
    such lines with the previous title.

    Args:
        cell: A BeautifulSoup `<td>` element containing film titles.

    Returns:
        A list of film titles with distributor codes.
    """
    lines = [l.strip() for l in cell.get_text("\n").split('\n') if l.strip()]
    titles: list[str] = []
    for line in lines:
        # Lines starting with '(' or 'WA' belong to the previous title
        if line.startswith('(') or line.startswith('WA') or line == 'WA':
            if titles:
                titles[-1] += ' ' + line
            else:
                titles.append(line)
        else:
            titles.append(line)
    return titles


def fetch_events(today: datetime | None = None) -> list[tuple[datetime.date, str]]:
    """Fetch all upcoming film start dates and titles.

    Args:
        today: Only events on or after this date will be returned.  If
            `None`, the current date is used.

    Returns:
        A list of `(date, title)` tuples for each upcoming film.
    """
    if today is None:
        today = datetime.now()
    url = 'https://www.insidekino.com/DStarts/DStartplan.htm'
    response = requests.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, 'html.parser')
    events: list[tuple[datetime.date, str]] = []
    # The InsideKino page uses rows with class "auto-style68" for dates.
    for date_cell in soup.find_all('td', class_='auto-style68'):
        date_text = date_cell.get_text(strip=True)
        # Only parse rows that contain a year in the date text
        if not any(str(year) in date_text for year in range(today.year, today.year + 10)):
            continue
        try:
            event_date = parse_date(date_text)
        except Exception:
            # Skip malformed date strings
            continue
        # Skip past dates
        if event_date.date() < today.date():
            continue
        # The next table row contains the film titles across categories
        tr = date_cell.find_parent('tr')
        next_tr = tr.find_next_sibling('tr')
        titles: list[str] = []
        for td in next_tr.find_all('td'):
            titles.extend(parse_titles(td))
        # Join lines split across cells (e.g. "Plattfuß am" and "Nil (CRC) WA")
        merged: list[str] = []
        i = 0
        while i < len(titles):
            # If a title does not contain a parentheses and the next line does,
            # they belong together.
            if i + 1 < len(titles) and '(' not in titles[i] and '(' in titles[i + 1]:
                merged.append(titles[i] + ' ' + titles[i + 1])
                i += 2
            else:
                merged.append(titles[i])
                i += 1
        for title in merged:
            events.append((event_date.date(), title))
    return events


def write_ics(events: list[tuple[datetime.date, str]], output_file: Path) -> None:
    """Write events into an iCalendar (.ics) file.

    Creates an all‑day event for each film on its release date.  The
    calendar contains a name and timezone declaration suitable for
    German users (Europe/Berlin).

    Args:
        events: A list of `(date, title)` tuples.
        output_file: Path to the file that should be written.
    """
    lines: list[str] = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'CALSCALE:GREGORIAN',
        'X-WR-CALNAME:Deutsche Kinostarts',
        'X-WR-TIMEZONE:Europe/Berlin',
    ]
    for date, title in events:
        uid = uuid.uuid4()
        start = date.strftime('%Y%m%d')
        end = (date + timedelta(days=1)).strftime('%Y%m%d')
        lines.append('BEGIN:VEVENT')
        lines.append(f'DTSTART;VALUE=DATE:{start}')
        lines.append(f'DTEND;VALUE=DATE:{end}')
        lines.append(f'SUMMARY:{title}')
        lines.append(f'UID:{uid}')
        lines.append('END:VEVENT')
    lines.append('END:VCALENDAR')
    output_file.write_text('\n'.join(lines), encoding='utf-8')


def main(argv: list[str]) -> None:
    """Entry point of the script."""
    # Determine output path
    if len(argv) > 1:
        output_path = Path(argv[1])
    else:
        output_path = Path('kinostarts_calendar.ics')
    events = fetch_events()
    write_ics(events, output_path)
    print(f'Generated {len(events)} events and wrote to {output_path}')


if __name__ == '__main__':
    main(sys.argv)