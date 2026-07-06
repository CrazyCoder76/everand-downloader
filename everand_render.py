"""Phase 2: render captured page HTML into PDF files. Runs in a HEADLESS bundled
Chromium context because Playwright's page.pdf() only works headless. It never
navigates Everand (just set_content), so Cloudflare is not involved; cookies are
passed only so @font-face / <img> resources can be fetched.

Each captured column carries the reader's own asymmetric margins (large right/bottom
reserved for the reading UI). We re-crop to the actual content with a uniform margin:
  - text pages get a UNIFORM page size (the widest/tallest text block across the book),
    content centred horizontally and top-aligned, so partial pages keep natural bottom
    whitespace like a printed book instead of becoming odd tiny pages;
  - image-only pages (cover, part dividers) keep their own tight size.
Two passes are needed: pass 1 measures every page to find the uniform size, pass 2
renders."""

import math
import os

MARGIN = int(os.environ.get('EVERAND_MARGIN', '48') or '48')  # px around the content

# Base CSS: only neutralise the on-screen scale; keep the wrapper's own absolute box.
_BASE_CSS = ("@page{margin:0}*{box-sizing:border-box}"
             "html,body{margin:0;padding:0;background:#fff}"
             "[data-content-column]{transform:none !important}")

# Measure the tight content box. Text is measured via Range so the text_line's
# width:100% box doesn't inflate the width. Returns {x0,y0,x1,y1,hasText} or null.
_JS_MEASURE = r"""
() => {
  const range = document.createRange();
  let x0=1e9,y0=1e9,x1=-1e9,y1=-1e9,found=false,hasText=false;
  const push = (r) => {
    if (r.width>0 && r.height>0) {
      found=true;
      x0=Math.min(x0,r.left); y0=Math.min(y0,r.top);
      x1=Math.max(x1,r.right); y1=Math.max(y1,r.bottom);
    }
  };
  for (const el of document.querySelectorAll('span.text_line')) {
    range.selectNodeContents(el);
    const r = range.getBoundingClientRect();
    if (r.width>0 && r.height>0) hasText = true;
    push(r);
  }
  for (const el of document.querySelectorAll('[data-content-column] img')) {
    push(el.getBoundingClientRect());
  }
  if (!found) return null;
  return {x0, y0, x1, y1, hasText};
}
"""

# Move the column into a clipping frame of the target size, content top-aligned and
# (optionally) horizontally centred. overflow:hidden stops the tall column from
# spilling into extra sliver pages.
_JS_PLACE = r"""
(a) => {
  const cc = document.querySelector('[data-content-column]');
  const frame = document.createElement('div');
  frame.style.cssText = `position:relative;width:${a.W}px;height:${a.H}px;overflow:hidden;background:#fff;`;
  document.body.insertBefore(frame, document.body.firstChild);
  frame.appendChild(cc);
  cc.style.position = 'absolute';
  const leftMargin = a.center ? (a.W - (a.x1 - a.x0)) / 2 : a.M;
  cc.style.left = (leftMargin - a.x0) + 'px';
  cc.style.top  = (a.M - a.y0) + 'px';
  document.documentElement.style.cssText = `margin:0;padding:0;width:${a.W}px;height:${a.H}px;overflow:hidden;`;
  document.body.style.cssText = `margin:0;padding:0;width:${a.W}px;height:${a.H}px;overflow:hidden;`;
}
"""


def render_pages(playwright, pages_sorted, fontfaces, cache_dir, storage_state_path, log):
    """pages_sorted: list of (page_no, {html,w,h}). Returns list of written pdf paths."""
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(storage_state=storage_state_path, ignore_https_errors=True)
    rp = context.new_page()
    total = len(pages_sorted)

    def load(pg):
        html = (pg['html'] or '').replace('src="/', 'src="https://www.everand.com/')
        doc = ("<!doctype html><html><head><meta charset='utf-8'>"
               f"<style>{_BASE_CSS}{fontfaces}</style></head><body>{html}</body></html>")
        try:
            rp.set_content(doc, wait_until='networkidle', timeout=20000)
        except Exception:
            rp.set_content(doc, wait_until='load', timeout=20000)
        try:
            rp.evaluate("""async () => {
                await document.fonts.ready;
                await Promise.all([...document.images].map(i => i.decode().catch(() => {})));
            }""")
        except Exception:
            pass

    # --- pass 1: measure every page to find the uniform text-page size ---
    metas = []
    for i, (page_no, pg) in enumerate(pages_sorted, 1):
        load(pg)
        metas.append(rp.evaluate(_JS_MEASURE))
        if i % 25 == 0 or i == total:
            log(f'  measured {i}/{total}')
    text_boxes = [m for m in metas if m and m['hasText']]
    if text_boxes:
        uni_w = math.ceil(max(m['x1'] - m['x0'] for m in text_boxes) + 2 * MARGIN)
        uni_h = math.ceil(max(m['y1'] - m['y0'] for m in text_boxes) + 2 * MARGIN)
        log(f'  uniform text page: {uni_w}x{uni_h}px')
    else:
        uni_w = uni_h = None

    # --- pass 2: render ---
    files = []
    for i, (page_no, pg) in enumerate(pages_sorted, 1):
        load(pg)
        m = metas[i - 1]
        if m and m['hasText'] and uni_w:
            w, h = uni_w, uni_h
            rp.evaluate(_JS_PLACE, {**m, 'W': w, 'H': h, 'M': MARGIN, 'center': True})
        elif m:  # image-only page -> tight own size
            w = math.ceil((m['x1'] - m['x0']) + 2 * MARGIN)
            h = math.ceil((m['y1'] - m['y0']) + 2 * MARGIN)
            rp.evaluate(_JS_PLACE, {**m, 'W': w, 'H': h, 'M': MARGIN, 'center': False})
        else:  # truly blank page -> keep natural size
            w, h = pg.get('w') or 1015, pg.get('h') or 1544

        pdf_file = os.path.join(cache_dir, f'{page_no:05d}.pdf')
        rp.pdf(path=pdf_file, width=f'{w}px', height=f'{h}px', print_background=True)
        files.append(pdf_file)
        if i % 10 == 0 or i == total:
            log(f'  rendered {i}/{total}')

    context.close()
    browser.close()
    return files
