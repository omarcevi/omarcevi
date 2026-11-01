"""Keep the self-updating sections of the profile README current.

Rewrites only the lines between these markers in README.md:
  <!-- SPEAKING:START -->    ... from events.md in omarcevi/omarcevi.github.io (the file behind omarcevi.dev)
  <!-- WRITING:START -->     ... from the Medium feed
  <!-- OPEN_SOURCE:START --> ... merged PRs to other people's public repos, plus contributions.txt

Each source is independent: if one can't be reached, its section stays as it was, the
others still update, and the script exits 1 so the workflow run shows the failure.
Run by .github/workflows/update-profile.yml; safe to run locally too.
"""
import calendar
import datetime
import email.utils
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

USER = "omarcevi"
SITE = "https://omarcevi.dev"
EVENTS_URL = "https://raw.githubusercontent.com/omarcevi/omarcevi.github.io/main/events.md"
FEED_URL = "https://medium.com/feed/@omarcevi"
API = "https://api.github.com"
ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
EXTRA = ROOT / "contributions.txt"
ISTANBUL = datetime.timezone(datetime.timedelta(hours=3))  # Turkey has no daylight saving time

RECENT_EVENTS = 3
MAX_POSTS = 3
MAX_PRS = 5
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
# same order the site uses: the title links to the first of these that the event has
TITLE_LINK = ("guide", "video", "slides", "photos", "link")


class UpdateError(Exception):
    pass


# --------------------------------------------------------------- helpers ----
def md_escape(text):
    """Escape the characters that GitHub markdown would turn into formatting or HTML."""
    text = re.sub(r"([\\`*_\[\]])", r"\\\1", text)
    return text.replace("<", "&lt;")


def replace_section(text, name, body):
    """Swap the lines between <!-- NAME:START --> and <!-- NAME:END --> for body."""
    start, end = f"<!-- {name}:START -->", f"<!-- {name}:END -->"
    pattern = re.compile(re.escape(start) + r"\n.*?" + re.escape(end), re.S)
    if not pattern.search(text):
        raise UpdateError(f"{start} ... {end} not found in README.md")
    return pattern.sub(lambda _: f"{start}\n{body}\n{end}", text, count=1)


def update(page, sources):
    """Rebuild each named section from its source; a failing source leaves its section untouched."""
    errors = []
    for name, build in sources.items():
        try:
            page = replace_section(page, name, build())
        except Exception as exc:  # noqa: BLE001 - report every failure, keep going
            errors.append(f"{name}: {exc}")
    return page, errors


# -------------------------------------------------------------- speaking ----
def parse_events(text):
    """events.md: each '## Title' and its '- key: value' lines; anything before the first one is notes."""
    events, current = [], None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("## "):
            current = {"title": line[3:].strip()}
            events.append(current)
        elif current is not None:
            m = re.match(r"^- ([A-Za-z]+):(.*)$", line)
            if m:
                current[m.group(1)] = m.group(2).strip()
    return events


def _parts(date):
    return [int(p) for p in date.split("-")]


def _period_end(date):
    """'2026-10' -> 2026-10-31, '2023' -> 2023-12-31, so a partial date sorts and compares as its last day."""
    p = _parts(date)
    y, m = p[0], (p[1] if len(p) > 1 else 12)
    d = p[2] if len(p) > 2 else calendar.monthrange(y, m)[1]
    return datetime.date(y, m, d)


def _short_date(date):
    p = _parts(date)
    return f"{MONTHS[p[1] - 1][:3]} {p[0]}" if len(p) > 1 else str(p[0])


def _long_date(date):
    p = _parts(date)
    return " ".join(([str(p[2])] if len(p) > 2 else []) + ([MONTHS[p[1] - 1]] if len(p) > 1 else []) + [str(p[0])])


def _event_line(e, with_date=False):
    href = next((e[k] for k in TITLE_LINK if k in e), None)
    title = md_escape(e["title"])
    if href:
        title = f"[{title}]({SITE + href if href.startswith('/') else href})"
    bits = [title, md_escape(e.get("event") or _short_date(e["date"]))]
    if with_date:
        bits.append(_long_date(e["date"]))
    if e.get("type") == "workshop":
        bits.append("workshop")
    return " · ".join(bits)


def render_speaking(events, today):
    dated = [e for e in events if "date" in e]
    upcoming = sorted((e for e in dated if len(e["date"]) == 10 and _period_end(e["date"]) >= today),
                      key=lambda e: e["date"])
    past = sorted((e for e in dated if _period_end(e["date"]) < today),
                  key=lambda e: _period_end(e["date"]), reverse=True)
    lines = []
    if upcoming:
        lines += ["**Next:** " + _event_line(upcoming[0], with_date=True), ""]
    lines += ["- " + _event_line(e) for e in past[:RECENT_EVENTS]]
    lines += ["", f"[All talks and workshops →]({SITE}/#speaking)"]
    return "\n".join(lines)


# --------------------------------------------------------------- writing ----
def parse_medium(xml_bytes):
    """Posts from the Medium RSS feed, newest first, with the tracking query cut off the links."""
    posts = []
    for item in ET.fromstring(xml_bytes).iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").split("?")[0].strip()
        if title and link:
            posts.append({"date": email.utils.parsedate_to_datetime(item.findtext("pubDate")),
                          "title": title, "link": link})
    return sorted(posts, key=lambda p: p["date"], reverse=True)


def render_writing(posts):
    if not posts:
        raise UpdateError("the Medium feed had no posts")
    return "\n".join(f"- [{md_escape(p['title'])}]({p['link']}) · {p['date']:%b %Y}" for p in posts[:MAX_POSTS])


# ----------------------------------------------------------- open source ----
def clean_pr_title(title):
    """'fix(ui)!: #3036 parameter filtering' -> 'Parameter filtering'."""
    title = re.sub(r"^\w+(\([^)]*\))?!?:\s*", "", title.strip())
    title = re.sub(r"^#\d+\s*", "", title)
    return title[:1].upper() + title[1:]


def parse_extra(text):
    """contributions.txt: one pull request URL per line, optionally ' | Title to show'."""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        url, _, title = line.partition("|")
        out.append((url.strip(), title.strip() or None))
    return out


def pr_from_search(item):
    return {
        "repo": item["repository_url"].split("/repos/", 1)[1],
        "title": clean_pr_title(item["title"]),
        "url": item["html_url"],
        "date": item["pull_request"]["merged_at"],
    }


def pr_from_pull(pull, title=None):
    return {
        "repo": pull["base"]["repo"]["full_name"],
        "title": title or clean_pr_title(pull["title"]),
        "url": pull["html_url"],
        "date": pull["merged_at"] or pull["closed_at"],
    }


def render_contributions(prs):
    unique = {pr["url"]: pr for pr in prs}.values()
    newest = sorted(unique, key=lambda pr: pr["date"], reverse=True)[:MAX_PRS]
    if not newest:
        raise UpdateError("found no pull requests to other people's repos")
    return "\n".join(f"- **{pr['repo']}** · [{md_escape(pr['title'])}]({pr['url']})" for pr in newest)


# --------------------------------------------------------------- sources ----
def fetch(url):
    headers = {"User-Agent": "Mozilla/5.0 (omarcevi profile README sync)"}
    if url.startswith(API):
        headers["Accept"] = "application/vnd.github+json"
        if os.environ.get("GITHUB_TOKEN"):
            headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as resp:
        return resp.read()


def speaking(today):
    return render_speaking(parse_events(fetch(EVENTS_URL).decode("utf-8")), today)


def writing():
    return render_writing(parse_medium(fetch(FEED_URL)))


def open_source():
    query = urllib.parse.quote(f"is:pr is:public is:merged author:{USER} -user:{USER}")
    prs = [pr_from_search(item) for item in json.loads(fetch(f"{API}/search/issues?q={query}&per_page=50"))["items"]]
    extra = parse_extra(EXTRA.read_text(encoding="utf-8")) if EXTRA.exists() else []
    for url, title in extra:
        owner, repo, _, number = url.rstrip("/").split("/")[-4:]
        prs.append(pr_from_pull(json.loads(fetch(f"{API}/repos/{owner}/{repo}/pulls/{number}")), title))
    return render_contributions(prs)


def main():
    today = datetime.datetime.now(ISTANBUL).date()
    page = README.read_text(encoding="utf-8")
    new_page, errors = update(page, {
        "SPEAKING": lambda: speaking(today),
        "WRITING": writing,
        "OPEN_SOURCE": open_source,
    })
    if new_page != page:
        README.write_text(new_page, encoding="utf-8")
        print("Updated README.md.")
    else:
        print("README.md is already up to date.")
    for error in errors:
        print(f"Could not update {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
