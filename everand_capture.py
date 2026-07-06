"""Phase 1: navigate the paginated double-column Everand EPUB reader and capture
each page's positioned HTML. Runs in a NON-headless real-Chrome context (so it can
pass Cloudflare and stay logged in). Returns {page_number: {html, w, h}} + fontfaces.

The reader renders pages asynchronously with animated transitions, so every read is
done only after the DOM has settled (see wait_stable)."""

import base64
import hashlib
import os
import re
import time

# One round-trip that snapshots both columns, the page counter and nav button state.
JS_STATE = r"""
() => {
  const readCol = (cls) => {
    const col = document.querySelector('div.reader_column.' + cls);
    if (!col) return { present: false, ready: false };
    const wrap = col.querySelector('[data-content-column]');
    const line = col.querySelector('span.text_line');
    const img  = col.querySelector('img');
    const style = wrap ? (wrap.getAttribute('style') || '') : '';
    const wm = style.match(/width:\s*([0-9.]+)px/);
    const hm = style.match(/height:\s*([0-9.]+)px/);
    return {
      present: true,
      ready: !!wrap && (!!line || !!img) && wrap.innerHTML.length > 200,
      firstPos: line ? line.getAttribute('data-position')
                     : (img ? 'img:' + ((img.getAttribute('src') || '').slice(-48)) : null),
      html: wrap ? wrap.outerHTML : null,
      w: wm ? Math.round(parseFloat(wm[1])) : null,
      h: hm ? Math.round(parseFloat(hm[1])) : null,
    };
  };
  const cEl = document.querySelector('div.page_counter');
  const endEl = document.querySelector('.end_of_reading_alert');
  const nextBtn = document.querySelector('button.page_right.next_btn');
  const prevBtn = document.querySelector('button.page_left.prev_btn');
  return {
    left: readCol('left_column'),
    right: readCol('right_column'),
    counter: cEl ? cEl.innerText.trim() : '',
    ended: !!(endEl && endEl.offsetParent !== null),
    nextDisabled: nextBtn ? nextBtn.disabled : true,
    prevDisabled: prevBtn ? prevBtn.disabled : true,
  };
}
"""


def inline_fontfaces(context, css, log):
    """Download each @font-face .ttf with the logged-in context and embed it as a data:
    URI. The headless renderer runs on an opaque (about:blank) origin, so a normal
    cross-origin @font-face fetch to fonts.scribdassets.com fails CORS and the glyphs
    fall back to a default font — which, combined with the reader's aggressive negative
    word-spacing, makes text overlap. Embedding the bytes removes the network fetch
    entirely (also immune to the short-lived font token expiring)."""
    for url in set(re.findall(r"url\('([^']+)'\)", css)):
        try:
            resp = context.request.get(url, headers={'Referer': 'https://www.everand.com/'})
            if not resp.ok:
                log(f'  font fetch HTTP {resp.status} — skipped'); continue
            b64 = base64.b64encode(resp.body()).decode('ascii')
            css = css.replace(f"url('{url}')", f"url('data:font/ttf;base64,{b64}')")
            log(f'  embedded font ({len(b64) // 1000}KB base64)')
        except Exception as e:
            log(f'  font embed error: {e}')
    return css


def parse_counter(text):
    """'PAGE 103 OF 243' -> (103, 243); returns (None, None) if not parseable."""
    m = re.search(r'(\d+)\s+OF\s+(\d+)', text or '', re.I)
    return (int(m.group(1)), int(m.group(2))) if m else (None, None)


def get_state(page):
    return page.evaluate(JS_STATE)


def wait_stable(page, timeout=15.0):
    """Poll until the reader has finished its transition: both columns rendered (or the
    book has ended) AND two consecutive reads agree. Returns the settled state dict."""
    t0 = time.time()
    prev_key = None
    best = get_state(page)
    while time.time() - t0 < timeout:
        st = get_state(page)
        best = st
        left_page, _ = parse_counter(st['counter'])
        left_ready = st['left'].get('ready')
        right_ready = st['right'].get('ready') or st['nextDisabled']
        key = (st['left'].get('firstPos'), st['right'].get('firstPos'), left_page)
        if left_ready and right_ready and left_page is not None and key == prev_key:
            return st
        prev_key = key if (left_ready and left_page is not None) else None
        page.wait_for_timeout(350)
    return best


def _click_nav(page, selector):
    """Click a nav button via JS so an overlapping cookie banner can't intercept it."""
    return page.evaluate(
        "(sel) => { const b = document.querySelector(sel); if (b) { b.click(); return true; } return false; }",
        selector)


def goto_start(page, log):
    """Rewind to the first page. Stops when Previous is disabled OR the page counter
    stops decreasing (some books never disable Previous at the first page)."""
    stuck = 0
    last = None
    for i in range(400):
        st = wait_stable(page, timeout=8)
        cur, _ = parse_counter(st['counter'])
        if st['prevDisabled']:
            break
        if last is not None and cur is not None and cur >= last:
            stuck += 1
            if stuck >= 2:  # counter no longer decreasing -> reached the start
                break
        else:
            stuck = 0
        last = cur
        if not _click_nav(page, 'button.page_left.prev_btn'):
            break
        t0 = time.time()
        while time.time() - t0 < 5:
            page.wait_for_timeout(250)
            now, _ = parse_counter(get_state(page)['counter'])
            if now is not None and cur is not None and now < cur:
                break
        if i % 10 == 0:
            log(f'  rewinding to start... (page {cur})')
    return wait_stable(page)


def _col_hash(html):
    return hashlib.md5((html or '').encode('utf-8', 'ignore')).hexdigest()


# Fetch a URL in the reader page (same-origin, with cookies) and return a data: URI.
_JS_FETCH_DATA_URI = r"""
async (url) => {
  try {
    const r = await fetch(url);
    if (!r.ok) return null;
    const blob = await r.blob();
    return await new Promise((res) => {
      const fr = new FileReader();
      fr.onload = () => res(fr.result);
      fr.onerror = () => res(null);
      fr.readAsDataURL(blob);
    });
  } catch (e) { return null; }
}
"""


def inline_images(page, html, cache, log):
    """Replace <img src="/scepub/...?token=..."> with a data: URI, fetched now from the
    logged-in reader page while the token is still valid. Rendering happens minutes later
    on an opaque origin where these tokened URLs 404/expire, leaving images blank."""
    for src in set(re.findall(r'<img[^>]+src="([^"]+)"', html)):
        if src.startswith('data:'):
            continue
        if src not in cache:
            url = src if src.startswith('http') else 'https://www.everand.com' + src
            try:
                cache[src] = page.evaluate(_JS_FETCH_DATA_URI, url)
            except Exception:
                cache[src] = None
            log(f'  embedded image ({len(cache[src]) // 1000}KB)' if cache[src]
                else f'  image fetch failed: {src[:50]}')
        if cache.get(src):
            html = html.replace(f'src="{src}"', f'src="{cache[src]}"')
    return html


def capture_book(page, log):
    """Walk the whole book front-to-back, one screen (spread) at a time. Each tall
    reader column can hold several print pages, and the print-page counter is NOT
    unique per column, so columns are keyed by CONTENT HASH (not page number) to avoid
    dropping distinct columns. Advancing exactly one screen per click guarantees no
    screen is skipped; dedup handles the overlap at spread boundaries.

    Returns (ordered_pages, total) where ordered_pages is a list of {html, w, h} in
    reading order."""
    goto_start(page, log)
    ordered = []
    seen = set()
    img_cache = {}
    total = None
    no_new = 0
    max_pages = int(os.environ.get('EVERAND_MAX_PAGES', '0') or '0')

    for _ in range(3000):
        st = wait_stable(page)
        left_page, total = parse_counter(st['counter'])
        added = 0
        for side in ('left', 'right'):  # reading order: left column then right column
            col = st[side]
            if col.get('ready') and col.get('html'):
                h = _col_hash(col['html'])
                if h not in seen:
                    seen.add(h)
                    html = inline_images(page, col['html'], img_cache, log)
                    ordered.append({'html': html, 'w': col['w'], 'h': col['h']})
                    added += 1
        log(f'  screen ~page {left_page}/{total}  (+{added}, {len(ordered)} captured)')

        if max_pages and len(ordered) >= max_pages:
            log(f'  reached EVERAND_MAX_PAGES={max_pages}, stopping'); break
        if st['nextDisabled']:
            log('  next button disabled -> end of book'); break

        prev_pos = st['left'].get('firstPos')
        if not _click_nav(page, 'button.page_right.next_btn'):
            no_new += 1
            if no_new >= 3:
                log('  next button unavailable -> stopping'); break
            page.wait_for_timeout(500); continue

        # wait until the screen actually turns (left column content changes)
        changed = False
        t0 = time.time()
        while time.time() - t0 < 12:
            page.wait_for_timeout(300)
            s2 = get_state(page)
            if s2['nextDisabled']:
                changed = True; break
            if s2['left'].get('ready') and s2['left'].get('firstPos') != prev_pos:
                changed = True; break

        # end when the page stops turning OR no new content keeps arriving
        if not changed:
            no_new += 1
        else:
            no_new = 0 if added else no_new + 1
        if no_new >= 3:
            log('  no new content across screens -> end of book'); break

    return ordered, total
