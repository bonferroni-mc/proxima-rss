# proxima-rss

A daily tecbio, biotech, and science news digest. Fetches stories from 17 RSS feeds and preprint APIs, filters by keyword relevance, scores each story 1–99, and outputs a clean HTML digest.

## What it does

- Pulls from 15 RSS feeds (STAT News, BioPharma Dive, Endpoints News, FierceBiotech, FiercePharma, GEN, BioSpace, Nature, MIT Tech Review, Labiotech, In Vivo/Citeline, Nature Biotech, Nature Chem Bio, Nature Methods, Nature Comms Bio)
- Pulls preprints from bioRxiv and medRxiv via their JSON APIs
- Filters stories by a configurable keyword list (proximity biology, PROTAC, AI drug discovery, specific companies, etc.)
- Scores each story 1–99 based on keyword tier: highest-priority terms (molecular glue, PROTAC, XL-MS, named companies) score highest
- Outputs `~/digest.html` — stories grouped by date, sorted by score, with colored relevance badges
- Runs automatically at 7am daily via launchd

## Setup

**Install dependencies:**
```bash
pip3 install -r requirements.txt
```

**Run manually:**
```bash
python3 reader.py
```

This writes `~/digest.html`. Open it in any browser.

## Options

```bash
python3 reader.py                 # keyword-filtered (default)
python3 reader.py --today-only    # last 24 hours only
python3 reader.py --no-filter     # all stories, no keyword filter
python3 reader.py --today-only --no-filter
```

## Scoring

Each story that passes the keyword filter starts at a base score of 40. Points are added based on which keywords match:

| Tier | Examples | Points |
|---|---|---|
| Highest priority | molecular glue, PROTAC, XL-MS, Proxima Bio, Isomorphic Labs, Arvinas | +20 |
| Platform / technical | AI drug discovery, AlphaFold, geometric deep learning, structural proteomics | +10 |
| Field-level | techbio, small molecule, generative AI, drug target | +5 |
| Additional matches | each keyword match beyond the first | +3 |

Scores are capped at 99. Badge colors: green (70+), amber (50–69), red (below 50).

## Customization

Both the keyword list and scoring tiers live at the top of `reader.py`:

- `KEYWORDS` — the full filter list; a story must match at least one to appear
- `TIER_HIGH`, `TIER_MID`, `TIER_LOW` — scoring tiers
- `FEEDS` — add or remove RSS feed URLs here
- `OUTPUT_FILE` — where the HTML digest is written (default: `~/digest.html`)

## Scheduling

A launchd job runs `reader.py` every morning at 7am and writes a fresh `~/digest.html`. Unlike cron, launchd will run the job after wake if the Mac was asleep at 7am.

```bash
# check the job is registered
launchctl list | grep proxima

# run it right now
launchctl start com.proxima.rss

# view the log
cat ~/proxima-rss/reader.log

# disable
launchctl unload ~/Library/LaunchAgents/com.proxima.rss.plist
```

The launchd plist is at `~/Library/LaunchAgents/com.proxima.rss.plist`.
