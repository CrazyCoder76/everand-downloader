"""Everand -> PDF downloader (rewritten for Everand's paginated double-column reader).

Usage:  python run.py <book_url>

Two phases:
  1) Real-Chrome, non-headless, persistent profile: log in (once), pass Cloudflare,
     walk the reader and capture every page's HTML.
  2) Headless Chromium: render each captured page to a PDF, then merge.

The persistent profile in ./chrome-profile keeps the login + Cloudflare clearance,
so only the very first run needs a manual login."""

import os
import sys
import shutil

from playwright.sync_api import sync_playwright
from PyPDF2 import PdfMerger

import everand_capture as capture
import everand_render as render


def log(msg):
    print(msg, flush=True)


def coverage_report(pages, total):
    if not pages:
        return "no pages captured"
    # pages are content-keyed columns (each may span several print pages), so the
    # column count need not equal the print-page counter; report both.
    return f"captured {len(pages)} page-columns (reader print-page total: {total})"


def main():
    if len(sys.argv) < 2:
        sys.exit("usage: python run.py <book_url>")
    book_url = sys.argv[1]

    book_filename = book_url.split('/')[5]
    cache_dir = os.path.join(os.getcwd(), book_filename)
    os.makedirs(cache_dir, exist_ok=True)
    profile_dir = os.path.join(os.getcwd(), 'chrome-profile')
    storage_path = os.path.join(cache_dir, '_session_state.json')

    with sync_playwright() as playwright:
        # --- Phase 1: capture (real Chrome, visible, persistent, logged in) ---
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            channel="chrome",
            headless=False,
            # Landscape viewport so the reader lays out each column at normal book-page
            # proportions (~2:3). A tall viewport stretches columns into long, odd pages.
            viewport={'width': 1600, 'height': 1080},
            ignore_https_errors=True,
            args=['--disable-blink-features=AutomationControlled'],
        )
        context.set_extra_http_headers({'Accept-Language': 'en-US,en;q=0.9'})

        page = context.new_page()
        page.goto('https://www.everand.com', wait_until='domcontentloaded')

        # First run: log in manually + solve Cloudflare/captcha in the visible window.
        log('Waiting for login (log in + solve any captcha in the browser window)...')
        page.locator("div.user_row").wait_for(state='attached', timeout=0)
        log('Logged in successfully.')

        log('Loading viewer...')
        page.goto(book_url.replace('/book/', '/read/'), wait_until='domcontentloaded')

        if 'Browser limit exceeded' in page.content():
            context.close()
            sys.exit('Browser limit exceeded: too many devices recently; wait up to 24h.')

        # best-effort: dismiss the cookie banner so it never overlays the nav buttons
        try:
            page.locator('button.osano-cm-accept-all').click(timeout=3000)
        except Exception:
            pass

        page.locator('#fontfaces').wait_for(state='attached', timeout=60000)
        fontfaces = page.locator('#fontfaces').inner_html()
        log('Embedding fonts...')
        fontfaces = capture.inline_fontfaces(context, fontfaces, log)

        log('Capturing pages...')
        pages, total = capture.capture_book(page, log)
        log(coverage_report(pages, total))

        context.storage_state(path=storage_path)
        context.close()

        if not pages:
            sys.exit('No pages captured — the reader layout may have changed again.')

        # debug: persist captured HTML so render CSS can be tuned offline (no re-nav)
        if os.environ.get('EVERAND_DUMP'):
            import json
            with open('_pages_dump.json', 'w', encoding='utf-8') as f:
                json.dump({'fontfaces': fontfaces, 'pages': pages}, f)
            log(f'  dumped {len(pages)} pages -> _pages_dump.json')

        # --- Phase 2: render (headless, page.pdf works here) ---
        log('Rendering pages to PDF...')
        pages_sorted = list(enumerate(pages, 1))  # (sequential page_no, {html,w,h})
        pdf_files = render.render_pages(
            playwright, pages_sorted, fontfaces, cache_dir, storage_path, log)

    log('Merging PDF pages...')
    merger = PdfMerger()
    for f in pdf_files:
        merger.append(f)
    out_pdf = f'{book_filename}.pdf'
    merger.write(out_pdf)
    merger.close()

    shutil.rmtree(cache_dir, ignore_errors=True)
    log(f'Download completed: {out_pdf}  ({len(pdf_files)} pages)')


if __name__ == '__main__':
    main()
