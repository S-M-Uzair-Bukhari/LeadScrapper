# Multi-Platform Lead Generator

A Python CLI that collects job leads from Upwork, Vollna, Freelancer, Guru,
and Bark, qualifies them, keeps US/Canada/Remote opportunities, and exports
the results to CSV/JSON and optionally Google Sheets.

## Architecture

This project is a concurrent, queue-oriented modular monolith. Platform
scrapers run independently, while all results pass through one shared
processing and output pipeline.

```text
main.py
   |
   v
LeadEngine
   |
   v
PlatformScheduler
   +-- Upwork worker ----------+
   +-- Upwork Selenium worker -+
   +-- Vollna worker ----------+--> keyword results
   +-- Freelancer worker ------+
   +-- Guru worker ------------+
   +-- Bark worker ------------+
                               |
                               v
                      Shared lead pipeline
                               |
                   normalize to JobLead
                               |
                       global deduplicate
                               |
                       analyze and score
                               |
                    US/Canada/Remote filter
                               |
                +--------------+--------------+
                |                             |
                v                             v
        SQLite checkpoint              Sheets buffer
                                              |
                                      upload every 10
                                              |
                                              v
                                  platform + dated tabs
                |
                v
        final CSV or JSON
```

Platforms run concurrently with a bounded worker pool. Within each platform,
keywords are processed sequentially so that existing HTTP sessions, browser
sessions, login state, and scraper-level deduplication continue to behave as
before. Browser-capable adapters also share a separate bounded semaphore so
that Chrome sessions do not grow without limit.

The platform scraper implementations retain their original selectors,
requests, parsing, login, and fallback behavior. The adapter layer only gives
them a common `scrape(keyword)` interface.

## Processing lifecycle

For every keyword result:

1. Convert platform output to the shared `JobLead` model.
2. Remove duplicate titles across the current run.
3. Extract business information and calculate the lead score.
4. Keep only US, Canada, or Remote leads.
5. Save the qualified lead to `data/leads.db`.
6. Add it to the platform's Google Sheets buffer.
7. Upload when that buffer reaches 10 leads.
8. Flush fewer than 10 remaining leads when the platform finishes.
9. Write one final timestamped CSV or JSON after all platforms finish.

Only one component writes to Google Sheets. Platform workers never write to
Sheets directly, preventing concurrent append and worksheet-creation races.

## Project layout

```text
upwork_scraper/
|-- config.py                  runtime configuration
|-- models.py                  shared JobLead model
|-- analyzer.py                extraction, scoring, and classification
|-- engine.py                  backward-compatible LeadEngine import
|
|-- platforms/
|   |-- base.py                common adapter
|   `-- registry.py            wraps existing scraper classes
|
|-- orchestration/
|   |-- engine.py              application coordinator
|   |-- scheduler.py           bounded platform concurrency
|   `-- events.py              worker-to-engine messages
|
|-- pipeline/
|   |-- processor.py           processing stage coordinator
|   |-- deduplicator.py        thread-safe run deduplication
|   `-- location_filter.py     US/Canada/Remote filtering
|
|-- storage/
|   `-- sqlite_repository.py   durable qualified-lead checkpoints
|
|-- exporters/
|   |-- local.py               CSV/JSON export
|   |-- sheets.py              single-writer batch upload
|   |-- rows.py                output row conversion
|   `-- schema.py              stable headers and tab mappings
|
|-- scraper.py                 existing Upwork fallback scraper
|-- selenium_scraper.py        existing authenticated Upwork scraper
|-- vollna.py                  existing Vollna RSS scraper
|-- freelancer.py              existing Freelancer scraper
|-- guru.py                    existing Guru scraper
`-- bark_scraper.py            preserved but temporarily disabled
```

## Installation

Python 3.10 or newer is recommended.

```powershell
python -m pip install -r requirements.txt
```

Chrome is required for the authenticated Upwork and Bark workers.

## Environment configuration

Create a `.env` file in the project root:

```dotenv
UPWORK_USERNAME=
UPWORK_PASSWORD=

BARK_USERNAME=
BARK_PASSWORD=

GOOGLE_SHEET_ID=
GOOGLE_CREDENTIALS_PATH=service-account.json
```

Google Sheets upload is disabled when `GOOGLE_SHEET_ID` is empty. Local
SQLite and CSV/JSON output still operate.

Do not commit `.env` or the Google service-account JSON file.

## Running

Run every configured platform and keyword:

```powershell
python main.py
```

Run selected platforms:

```powershell
python main.py -p upwork freelancer guru
```

Run selected keywords:

```powershell
python main.py -k "react developer" "shopify development"
```

Limit results per keyword:

```powershell
python main.py -r 20
```

Passing `-r` disables the adaptive daily policy for that run so the explicit
CLI value is respected.

Export JSON:

```powershell
python main.py --format json
```

Show detailed logs:

```powershell
python main.py -v
```

By default, one command starts a session of 10 runs. Each completed run is
followed by a 30-second wait. The first eligible run uses catch-up mode; after
that successful checkpoint, later session runs use normal mode.

Run only once:

```powershell
python main.py --runs 1
```

Keep running until manually stopped with `Ctrl+C`:

```powershell
python main.py --continuous
```

Change the delay or session limit:

```powershell
python main.py --runs 10 --interval 30
```

## Runtime configuration

The main structural settings are in `ScraperConfig`:

| Setting | Default | Meaning |
|---|---:|---|
| `max_platform_workers` | `4` | Maximum platform workers running concurrently |
| `max_browser_workers` | `2` | Maximum browser-capable searches running concurrently |
| `event_queue_size` | `100` | Maximum keyword-result batches awaiting processing |
| `max_results_per_keyword` | `50` | Result cap returned by each platform search |
| `google_sheet_tab` | `Leads` | Single worksheet receiving every platform |
| `sheets_batch_size` | `5` | Eligible leads per streaming Sheets upload |
| `sheets_min_lead_score` | `30` | Minimum score saved to Google Sheets |
| `sheets_min_write_interval` | `1.1` | Minimum seconds between Sheets write requests |
| `sheets_retry_attempts` | `5` | Attempts for quota and temporary API failures |
| `sheets_quota_cooldown` | `60` | Cooldown after a batch exhausts its retries |
| `database_path` | `data/leads.db` | SQLite checkpoint database |
| `output_dir` | `output` | Final CSV/JSON directory |
| `output_format` | `csv` | Local output format |

## Adaptive daily collection

Daily mode is enabled by default and uses the computer's local calendar date.
The default policy timezone is `Asia/Karachi`, and run state is stored in
`data/leads.db`. Set `SCRAPER_TIMEZONE` in `.env` to use another IANA timezone
such as `America/New_York`.

| Daily run | Jobs per keyword | Page/scroll limit | Posted-time behavior |
|---|---:|---:|---|
| First or catch-up run | Up to 1,000 | Up to 100 | Continue until reaching jobs older than 14 hours |
| Later runs | 20 | 2 | Keep newest-first platform results |

A catch-up run is selected for the first run of the local day or whenever at
least 14 hours have elapsed since the last successfully completed run. Started
or aborted runs do not suppress catch-up mode. The window means “not older
than 14 hours.” The high result/page limits are safety ceilings: paginated
scrapers stop earlier when a newest-first page reaches the lookback boundary
or the platform has no more results.

Platform mapping:

- Upwork Selenium and Bark treat the page limit as scroll/load batches.
- Freelancer and Guru request up to that many result pages.
- Upwork direct/Wayback attempts up to that many pages or snapshots.
- Vollna is an RSS feed, so it has no page concept; only the job limit applies.

Upwork, Vollna, Bark, and dated Guru records can be filtered using their
posting timestamps. Freelancer exposes a bid deadline such as `6 days left`,
not a reliable posting timestamp. Unparseable timestamps are retained from
newest-first results by default (`keep_unknown_posted_dates=True`) rather than
being incorrectly classified as old.

To disable adaptive mode:

```powershell
python main.py --no-adaptive-daily
```

To force and test a catch-up immediately, without changing database history:

```powershell
python main.py --catch-up
```

## Output behavior

Local output is written after the complete run:

```text
output/leads_YYYYMMDD_HHMMSS.csv
```

Qualified leads are also checkpointed immediately in SQLite:

```text
data/leads.db
```

When Sheets is enabled, leads are written to:

- A cumulative platform tab, such as `Upwork`.
- A dated platform tab, such as `Upwork 2026-07-29`.

Existing sheet titles are not appended again. Row colors represent priority:

- Green: high-priority lead
- Yellow: possible lead
- Red: low-priority lead

Sheets use a canonical header row, fixed column widths, fixed row heights, and
clipped long text. The first row is frozen and filters remain enabled, keeping
large descriptions and URLs from resizing the worksheet.

Every lead row also records:

- `Lead Found At`: UTC time when the scraper created the `JobLead`.
- `Sheet Saved At`: local time when that batch was sent to Google Sheets.
- `Found-to-Sheet Seconds`: elapsed seconds between those timestamps.

Existing sheets using the previous 23-column schema are migrated by inserting
these three columns after `Date Posted`, preserving the alignment of older
lead data.

All platforms are stored in one `Leads` worksheet and identified by the
`Job Platform` column. New five-lead batches are inserted directly below the
header while scraping is still running. The newest discovery timestamp is
placed first within each batch, while existing rows shift downward.

After the qualified lead summary, the CLI prints the complete run duration:

```text
Total scraper run time: 01:02:03 (3723.40 seconds)
```

This covers platform scraping, processing, SQLite checkpoints, Sheets flushes,
quota waits/retries, and the final local export.

## Lead scoring and Sheet eligibility

Important positive weights include:

- Company website: 25
- Company name: 15
- Business email: 20 (general email: 10)
- Decision-maker: 10
- Non-empty job description: 10
- Budget, matching service, long-term opportunity, and business clue: 10 each

Priority is based strictly on the final 0–100 score:

| Score | Priority | Google Sheets |
|---:|---|---|
| 0–29 | RED | Not uploaded |
| 30–49 | RED | Uploaded |
| 50–69 | YELLOW | Uploaded |
| 70–100 | GREEN | Uploaded |

Scores below 30 remain available in SQLite and local CSV/JSON exports. Unique,
recency, and location filtering continue to run before this Sheets cutoff.

## Failure behavior

- A keyword failure is logged and its platform continues with the next keyword.
- A platform failure does not stop other platform workers.
- Qualified leads saved before a later failure remain in SQLite.
- Sheets writes are globally rate-limited to stay below the per-user quota.
- Quota and temporary API failures use bounded exponential backoff and honor
  Google's `Retry-After` header when present.
- A batch that exhausts its retries remains buffered, enters a 60-second
  cooldown, and is retried during a later or final flush.
- Browser and HTTP resources are closed when the CLI exits.

SQLite provides durable checkpoints, but automatic resume from a previous
run is not enabled yet. A future resume command can replay records whose
`uploaded` value is `0`.

## Tests

Run the offline structural tests:

```powershell
python -m unittest tests.test_structure -v
```

Run the analyzer sample suite:

```powershell
python test_qualification.py
```

The structural tests do not call external platforms or Google Sheets.
