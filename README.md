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
`-- bark_scraper.py            existing Bark scraper
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

Export JSON:

```powershell
python main.py --format json
```

Show detailed logs:

```powershell
python main.py -v
```

## Runtime configuration

The main structural settings are in `ScraperConfig`:

| Setting | Default | Meaning |
|---|---:|---|
| `max_platform_workers` | `4` | Maximum platform workers running concurrently |
| `max_browser_workers` | `2` | Maximum browser-capable searches running concurrently |
| `event_queue_size` | `100` | Maximum keyword-result batches awaiting processing |
| `max_results_per_keyword` | `50` | Result cap returned by each platform search |
| `sheets_batch_size` | `10` | Qualified leads per Sheets upload |
| `sheets_min_write_interval` | `1.1` | Minimum seconds between Sheets write requests |
| `sheets_retry_attempts` | `5` | Attempts for quota and temporary API failures |
| `sheets_quota_cooldown` | `60` | Cooldown after a batch exhausts its retries |
| `database_path` | `data/leads.db` | SQLite checkpoint database |
| `output_dir` | `output` | Final CSV/JSON directory |
| `output_format` | `csv` | Local output format |

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
- `Sheet Saved At`: UTC time when that batch was sent to Google Sheets.
- `Found-to-Sheet Seconds`: elapsed seconds between those timestamps.

Existing sheets using the previous 23-column schema are migrated by inserting
these three columns after `Date Posted`, preserving the alignment of older
lead data.

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
