#!/usr/bin/env python3
import argparse
import feedparser
import json
import re
import socket
import sys
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

FEEDS = [
    ("STAT News",             "https://www.statnews.com/feed/"),
    ("BioPharma Dive",        "https://www.biopharmadive.com/feeds/news/"),
    ("Endpoints News",        "https://endpoints.news/feed/"),
    ("FierceBiotech",         "https://www.fiercebiotech.com/rss/xml"),
    ("FiercePharma",          "https://www.fiercepharma.com/rss/xml"),
    ("GEN",                   "https://www.genengnews.com/feed/"),
    ("BioSpace",              "https://www.biospace.com/index.rss"),
    ("Nature",                "https://www.nature.com/nature.rss"),
    ("MIT Tech Review Bio",   "https://www.technologyreview.com/feed/"),
    ("Labiotech",             "https://www.labiotech.eu/feed/"),
    ("In Vivo (Citeline)",    "https://insights.citeline.com/arc/outboundfeeds/rss/category/in-vivo/"),
    ("Nature Biotech",        "https://www.nature.com/nbt/current_issue.rss"),
    ("Nature Chem Bio",       "https://www.nature.com/nchembio/current_issue.rss"),
    ("Nature Methods",        "https://www.nature.com/nmeth/current_issue.rss"),
    ("Nature Comms Bio",      "https://www.nature.com/commsbio/current_issue.rss"),
]

OUTPUT_FILE = Path.home() / "digest.html"
NO_DATE = datetime.min.replace(tzinfo=timezone.utc)

KEYWORDS = [
    # proximity biology & degraders
    "molecular glue", "PROTAC", "protein degrader", "targeted protein degradation",
    "protein degradation", "induced proximity", "proximity biology", "proximity therapeutic",
    "ternary complex", "E3 ligase", "cereblon", "CRBN", "molecular glue degrader", "RIPTAC",
    # structural & chemical biology
    "cross-linking mass spectrometry", "XL-MS", "protein-protein interaction",
    "structural proteomics", "protein structure", "protein folding", "AlphaFold",
    "chemical biology", "medicinal chemistry", "phenotypic screening", "structure prediction",
    "small molecule",
    # AI & computational
    "AI drug discovery", "AI-native biotech", "techbio", "foundation model protein",
    "geometric deep learning", "computational biology", "machine learning drug",
    "generative AI", "open source model",
    # drug discovery & development
    "drug discovery", "drug target", "undruggable", "clinical trial", "FDA approval",
    "cancer biology", "cell biology", "oncology", "immunology", "cardiometabolic",
    "rare disease",
    # companies
    "Proxima Bio", "NeoLink", "Neo-1", "Fathom Therapeutics", "Isomorphic Labs",
    "Chai Discovery", "Arvinas", "vepdegestrant", "VEPPANU", "Nurix", "Kymera",
    "Monte Rosa", "Recursion Pharmaceuticals", "Iambic",
    # industry & business
    "biopharma", "biotech platform", "platform company", "R&D strategy",
    "partnership deal", "Series A", "Series B", "venture capital biotech",
    "DCVC", "NVentures", "Flagship Pioneering", "Atlas Venture", "Third Rock",
    "ARCH Venture", "a16z bio",
    # preprints
    "bioRxiv", "preprint",
]

# +20 each
TIER_HIGH = {kw.lower() for kw in [
    "molecular glue", "molecular glue degrader", "PROTAC", "protein degrader",
    "targeted protein degradation", "protein degradation", "induced proximity",
    "proximity biology", "proximity therapeutic", "ternary complex",
    "E3 ligase", "cereblon", "CRBN", "RIPTAC",
    "XL-MS", "cross-linking mass spectrometry",
    "Proxima Bio", "NeoLink", "Neo-1", "Fathom Therapeutics", "Isomorphic Labs",
    "Chai Discovery", "Arvinas", "vepdegestrant", "VEPPANU", "Nurix", "Kymera",
    "Monte Rosa",
]}

# +10 each
TIER_MID = {kw.lower() for kw in [
    "AI drug discovery", "foundation model protein", "protein structure", "protein folding",
    "geometric deep learning", "computational biology", "AlphaFold",
    "structural proteomics", "protein-protein interaction",
    "AI-native biotech", "undruggable",
]}

# +5 each
TIER_LOW = {kw.lower() for kw in [
    "biotech platform", "drug target", "small molecule", "generative AI", "techbio",
    "chemical biology", "medicinal chemistry", "phenotypic screening",
    "structure prediction", "machine learning drug", "open source model",
]}

BIORXIV_CATEGORIES = {
    "bioinformatics", "genomics", "systems biology", "synthetic biology",
    "pharmacology and toxicology", "bioengineering", "cell biology",
    "biochemistry", "genetics", "molecular biology",
}


def strip_html(text):
    text = re.sub(r"<[^>]+>", "", text)
    for ent, ch in [("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&#39;", "'")]:
        text = text.replace(ent, ch)
    return text.strip()


def escape_html(text):
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))


def entry_text(entry):
    return " ".join(
        strip_html(entry.get(f, "")) for f in ("title", "summary", "description", "abstract")
    ).lower()


def score_entry(entry):
    text = entry_text(entry)
    matched = [kw for kw in KEYWORDS if kw.lower() in text]
    if not matched:
        return 0
    score = 40
    for kw in matched:
        k = kw.lower()
        if k in TIER_HIGH:
            score += 20
        elif k in TIER_MID:
            score += 10
        elif k in TIER_LOW:
            score += 5
    score += max(0, len(matched) - 1) * 3
    return min(99, score)


def parse_date(entry):
    for field in ("published", "updated"):
        raw = entry.get(field)
        if raw:
            try:
                return parsedate_to_datetime(raw).astimezone(timezone.utc)
            except Exception:
                try:
                    return datetime.fromisoformat(raw.rstrip("Z")).replace(tzinfo=timezone.utc)
                except Exception:
                    pass
    return NO_DATE


FEED_TIMEOUT = 10


def fetch_feed(name, url):
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        })
        with urllib.request.urlopen(req, timeout=FEED_TIMEOUT) as response:
            content = response.read()
        parsed = feedparser.parse(content)
        return name, parsed.entries, None
    except (socket.timeout, TimeoutError):
        return name, [], f"timed out after {FEED_TIMEOUT}s"
    except Exception as e:
        return name, [], str(e)


def fetch_preprint_server(server, display_name, categories=None):
    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    url = f"https://api.biorxiv.org/details/{server}/{yesterday}/{today}/0/json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "proxima-rss/1.0"})
        with urllib.request.urlopen(req, timeout=FEED_TIMEOUT) as response:
            data = json.loads(response.read())
        entries = []
        for item in data.get("collection", []):
            if categories and item.get("category", "").lower() not in categories:
                continue
            entries.append({
                "title":    item.get("title", "(no title)"),
                "link":     f"https://www.{server}.org/abs/{item.get('doi', '')}",
                "published": item.get("date", ""),
                "abstract": item.get("abstract", ""),
            })
        return display_name, entries, None
    except (socket.timeout, TimeoutError):
        return display_name, [], f"timed out after {FEED_TIMEOUT}s"
    except Exception as e:
        return display_name, [], str(e)


def badge_color(score):
    if score >= 70:
        return "#16a34a", "#dcfce7"   # green
    elif score >= 50:
        return "#b45309", "#fef9c3"   # yellow/amber
    else:
        return "#b91c1c", "#fee2e2"   # red


def render_html(by_day, day_order, total, fetched_at, no_filter):
    sections = []
    for day in day_order:
        stories = sorted(by_day[day], key=lambda x: x[0], reverse=True)
        rows = []
        for score, source, entry in stories:
            title    = escape_html(strip_html(entry.get("title", "(no title)")))
            link     = entry.get("link", "#").strip()
            date     = parse_date(entry)
            date_str = date.strftime("%b %d, %Y") if date != NO_DATE else "unknown date"
            fg, bg   = badge_color(score)
            rows.append(f"""
        <div class="story">
          <div class="story-top">
            <span class="badge" style="color:{fg};background:{bg}">{score}</span>
            <a href="{link}" class="story-title" target="_blank" rel="noopener">{title}</a>
          </div>
          <div class="story-meta">{escape_html(source)}&ensp;·&ensp;{date_str}</div>
        </div>""")

        sections.append(f"""
      <section>
        <h2 class="date-header">{escape_html(day)}</h2>
        {"".join(rows)}
      </section>""")

    filter_note = "" if not no_filter else '<p class="filter-note">Keyword filter disabled — showing all stories.</p>'
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Proxima RSS &mdash; {escape_html(fetched_at)}</title>
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background: #fff;
      color: #111;
      max-width: 780px;
      margin: 0 auto;
      padding: 2rem 1.5rem 4rem;
    }}
    header {{ border-bottom: 2px solid #111; padding-bottom: 1rem; margin-bottom: 2rem; }}
    header h1 {{ font-size: 1.6rem; font-weight: 700; letter-spacing: -0.02em; }}
    header p {{ color: #555; font-size: 0.875rem; margin-top: 0.25rem; }}
    .filter-note {{ font-size: 0.8rem; color: #888; margin-top: 0.5rem; }}
    .date-header {{
      font-size: 0.7rem; font-weight: 700; letter-spacing: 0.08em;
      text-transform: uppercase; color: #555;
      border-bottom: 1px solid #e5e7eb;
      padding-bottom: 0.4rem; margin: 2rem 0 0.75rem;
    }}
    .story {{ padding: 0.75rem 0; border-bottom: 1px solid #f3f4f6; }}
    .story-top {{ display: flex; align-items: baseline; gap: 0.6rem; }}
    .badge {{
      font-size: 0.7rem; font-weight: 700; letter-spacing: 0.02em;
      padding: 0.15rem 0.45rem; border-radius: 999px;
      white-space: nowrap; flex-shrink: 0;
    }}
    .story-title {{
      font-size: 0.95rem; font-weight: 500; color: #111;
      text-decoration: none; line-height: 1.4;
    }}
    .story-title:hover {{ text-decoration: underline; color: #1d4ed8; }}
    .story-meta {{ font-size: 0.8rem; color: #6b7280; margin-top: 0.3rem; padding-left: 2.1rem; }}
    footer {{ margin-top: 3rem; font-size: 0.8rem; color: #9ca3af; border-top: 1px solid #e5e7eb; padding-top: 1rem; }}
  </style>
</head>
<body>
  <header>
    <h1>Proxima RSS</h1>
    <p>Biotech &amp; Science News &mdash; {escape_html(fetched_at)}</p>
    {filter_note}
  </header>
  {"".join(sections)}
  <footer>{total} stories fetched across {len(FEEDS) + 2} feeds</footer>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--today-only", action="store_true", help="Show only stories from the last 24 hours")
    parser.add_argument("--no-filter",  action="store_true", help="Disable keyword filtering")
    args = parser.parse_args()

    fetched_at = datetime.now().strftime("%B %d, %Y at %H:%M")
    print(f"Fetching feeds...", file=sys.stderr)

    all_stories = []

    for name, url in FEEDS:
        print(f"  {name}", file=sys.stderr)
        source_name, entries, error = fetch_feed(name, url)
        if error:
            print(f"  ⚠  {source_name}: {error}", file=sys.stderr)
            continue
        for entry in entries:
            all_stories.append((parse_date(entry), source_name, entry))

    for server, display_name, categories in [
        ("biorxiv", "bioRxiv", BIORXIV_CATEGORIES),
        ("medrxiv", "medRxiv", None),
    ]:
        print(f"  {display_name}", file=sys.stderr)
        source_name, entries, error = fetch_preprint_server(server, display_name, categories)
        if error:
            print(f"  ⚠  {display_name}: {error}", file=sys.stderr)
        else:
            for entry in entries:
                all_stories.append((parse_date(entry), source_name, entry))

    # score and filter
    scored = []
    for date, source, entry in all_stories:
        score = score_entry(entry)
        if args.no_filter or score > 0:
            scored.append((date, score, source, entry))

    # date filter
    if args.today_only:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        scored = [(d, sc, s, e) for d, sc, s, e in scored if d == NO_DATE or d >= cutoff]

    # group by day
    by_day = defaultdict(list)
    day_order = []
    for date, score, source, entry in sorted(scored, key=lambda x: x[0], reverse=True):
        day = date.strftime("%A, %B %d, %Y") if date != NO_DATE else "Unknown Date"
        if day not in by_day:
            day_order.append(day)
        by_day[day].append((score, source, entry))

    total = sum(len(v) for v in by_day.values())
    html = render_html(by_day, day_order, total, fetched_at, args.no_filter)

    OUTPUT_FILE.write_text(html, encoding="utf-8")
    print(f"\nWrote {total} stories to {OUTPUT_FILE}", file=sys.stderr)


if __name__ == "__main__":
    main()
