# scribd (everand) → PDF downloader

Download eBooks you have access to on [Everand](https://www.everand.com) (formerly
Scribd) as clean, **text‑selectable** PDFs for personal, offline use.

> Only Everand **eBooks** are supported (not Documents or audiobooks). Use only with
> your own Everand account, for personal use, and respect Everand's Terms of Service.

## How it works

Everand's reader is a paginated, Cloudflare‑protected EPUB viewer, so the tool:

1. Opens the book in **your real Google Chrome** (Playwright `channel="chrome"`) with a
   persistent profile — you log in once and pass Cloudflare like a normal browser.
2. Walks the reader one screen at a time, capturing each page's positioned HTML. Pages
   are keyed by content hash (each tall column holds several print pages), so nothing is
   skipped or duplicated.
3. Embeds the book's fonts and renders every page to a vector PDF, cropped to a clean,
   uniform book‑page layout, then merges them into one file.

Code layout: `run.py` (orchestrator) · `everand_capture.py` (phase 1: navigate +
capture) · `everand_render.py` (phase 2: render + crop to PDF).

## Installation

```
pip install -r requirements.txt
python -m playwright install chromium
```

Requirements: Python 3.9+, and **Google Chrome installed** (the tool drives real Chrome,
not the bundled Chromium).

## Usage (single book)

```
python run.py "<everand_book_url>"
```

Example:

```
python run.py "https://www.everand.com/read/813249861/Sleep-Change-the-way-you-sleep-with-this-90-minute-read"
```

1. On the **first run** a Chrome window opens — log in to Everand and solve any captcha.
   Your login is saved in `./chrome-profile/`, so later runs are automatic.
2. To switch accounts, delete the `chrome-profile/` folder and run again.
3. The finished `<book>.pdf` is written next to the script.

Optional environment variables:

- `EVERAND_MARGIN=48` — page margin (px) around the text block.
- `EVERAND_MAX_PAGES=N` — stop after N pages (quick test).

## Batch mode (many books) — `main.py`

`main.py` reads a list of book URLs from a local MongoDB (`bookUrlList.books`) and runs
`run.py` for each. To scrape book URLs, see the companion project
[`everand-book-url-scraper`](https://github.com/CrazyCoder76/everand-book-url-scraper).
Batch mode is optional and not needed for single‑book downloads.

## Notes

- You can only download books your account has access to.
- If Everand changes its reader again, the DOM selectors in `everand_capture.py` may need
  updating.
