#!/usr/bin/env python3
"""
check_archives.py
- usage:
    python scripts/check_archives.py --email cye04720@nifty.com --candidates candidates.txt --out found_archives.txt --excerpt-out found_excerpts.txt
- Behavior:
  - Read candidates.txt (one URL per line). For each:
    - if it's a web.archive.org URL, fetch and test directly
    - otherwise query Wayback CDX for snapshots of the original URL using several patterns
    - for each snapshot, fetch HTML and search for mailto:<email>
    - if found, record snapshot URL and an excerpt (surrounding text)
  - Writes found_archives.txt and found_excerpts.txt
"""

import argparse
import re
import sys
import time
from urllib.parse import quote
import requests
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (compatible; MailtoFinder/1.0; +https://example.com)"
CDX_API_TEMPLATE = "https://web.archive.org/cdx/search/cdx?url={orig}&output=json&fl=timestamp,original&filter=statuscode:200&collapse=digest"

# gentle delay between snapshot fetches (seconds)
SLEEP_BETWEEN = 0.5

def fetch_text(url, timeout=30):
    headers = {"User-Agent": USER_AGENT}
    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.text

def find_mailto_occurrences(html_text, email):
    """
    Return list of (snippet, full_match) for occurrences of mailto link or mailto in text.
    snippet is a small context around the match (approx 120 chars).
    """
    results = []
    # look for href="mailto:...email..."
    href_pattern = re.compile(r'href\s*=\s*["\']\s*mailto\s*:\s*' + re.escape(email) + r'\s*["\']', re.IGNORECASE)
    for m in href_pattern.finditer(html_text):
        start = max(0, m.start() - 120)
        end = min(len(html_text), m.end() + 120)
        snippet = html_text[start:end].replace("\r", " ").replace("\n", " ")
        results.append((snippet, m.group(0)))
    # fallback: plain mailto:... anywhere
    plain_pattern = re.compile(r'mailto\s*:\s*' + re.escape(email), re.IGNORECASE)
    for m in plain_pattern.finditer(html_text):
        # avoid duplicates if already captured
        if href_pattern.search(html_text, max(0, m.start()-50), min(len(html_text), m.end()+50)):
            continue
        start = max(0, m.start() - 120)
        end = min(len(html_text), m.end() + 120)
        snippet = html_text[start:end].replace("\r", " ").replace("\n", " ")
        results.append((snippet, m.group(0)))
    return results

def query_cdx(orig_url):
    """Return list of (timestamp, original) from CDX or empty list on failure"""
    try:
        api = CDX_API_TEMPLATE.format(orig=quote(orig_url, safe=""))
        r = requests.get(api, headers={"User-Agent": USER_AGENT}, timeout=30)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"[!] CDX API error for {orig_url}: {e}", file=sys.stderr)
        return []
    if not isinstance(data, list) or len(data) < 2:
        return []
    rows = []
    for row in data[1:]:
        if isinstance(row, list) and len(row) >= 2:
            rows.append((row[0], row[1]))
    return rows

def scan_snapshot(snapshot_url, email):
    """Fetch snapshot and return list of snippets if mailto found"""
    try:
        html = fetch_text(snapshot_url)
    except Exception as e:
        print(f"[!] fetch failed for {snapshot_url}: {e}", file=sys.stderr)
        return []
    hits = find_mailto_occurrences(html, email)
    return hits

def process_archive_url(url, email, found_set, excerpts):
    """If URL is a direct archive URL, test it; otherwise query CDX and test snapshots."""
    if "web.archive.org" in url:
        # ignore wildcard-like candidate containing * (from patterns)
        if "*" in url:
            return
        print(f"[>] Direct archive URL: {url}")
        hits = scan_snapshot(url, email)
        if hits:
            found_set.add(url)
            for snip, full in hits:
                excerpts.append((url, full, snip))
        return

    # if the URL looks like a domain pattern (contains *) treat as CDX pattern directly
    if "*" in url:
        # CDX accepts patterns like *cye04720* (we will pass as-is)
        print(f"[>] Treating as CDX pattern: {url}")
        rows = query_cdx(url)
        for ts, orig in rows:
            snap = f"https://web.archive.org/web/{ts}id_/{orig}"
            print(f"    Checking {snap}")
            hits = scan_snapshot(snap, email)
            if hits:
                found_set.add(snap)
                for snip, full in hits:
                    excerpts.append((snap, full, snip))
            time.sleep(SLEEP_BETWEEN)
        return

    # otherwise treat as an original URL and ask CDX for snapshots
    print(f"[>] Querying CDX for original URL: {url}")
    rows = query_cdx(url)
    for ts, orig in rows:
        snap = f"https://web.archive.org/web/{ts}id_/{orig}"
        print(f"    Checking {snap}")
        hits = scan_snapshot(snap, email)
        if hits:
            found_set.add(snap)
            for snip, full in hits:
                excerpts.append((snap, full, snip))
        time.sleep(SLEEP_BETWEEN)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--email", required=True)
    p.add_argument("--candidates", default="candidates.txt")
    p.add_argument("--out", default="found_archives.txt")
    p.add_argument("--excerpt-out", default="found_excerpts.txt")
    args = p.parse_args()
    email = args.email.strip()

    # default fallback patterns to scan if candidates don't include them
    fallback_patterns = [
        "*cye04720*nifty.com*",
        "*.nifty.com/*",
        "*.so-net.ne.jp/*nymph*",
        "www008.upp.so-net.ne.jp/NYMPH/*",
        "www12.u-page.so-net.ne.jp:80/ka3/nymph-/*",
        "8028.teacup.com/*",
    ]

    try:
        with open(args.candidates, "r", encoding="utf-8") as f:
            candidates = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        candidates = []

    # if no candidates found from generation, seed the fallback patterns
    if not candidates:
        print("[*] No candidates provided; using fallback patterns.")
        candidates = list(fallback_patterns)

    found = set()
    excerpts = []

    # process candidates
    for u in candidates:
        try:
            process_archive_url(u, email, found, excerpts)
        except Exception as e:
            print(f"[!] Error processing {u}: {e}", file=sys.stderr)

    # if still empty, as a last effort, run CDX for a few patterns
    if not found:
        print("[*] No results yet — running focused CDX patterns as last effort.")
        for pat in fallback_patterns:
            try:
                process_archive_url(pat, email, found, excerpts)
            except Exception as e:
                print(f"[!] Error processing fallback pattern {pat}: {e}", file=sys.stderr)

    # write outputs
    if found:
        with open(args.out, "w", encoding="utf-8") as f:
            for s in sorted(found):
                f.write(s + "\n")
        print(f"[+] Wrote {len(found)} snapshots to {args.out}")
    else:
        print("[*] No snapshots matched; nothing written to", args.out)

    if excerpts:
        with open(args.excerpt_out, "w", encoding="utf-8") as f:
            for snap, full, snip in excerpts:
                f.write(f"--- {snap} ---\n")
                f.write(f"match: {full}\n")
                f.write(f"{snip}\n\n")
        print(f"[+] Wrote {len(excerpts)} excerpts to {args.excerpt_out}")
    else:
        print("[*] No excerpts found.")

if __name__ == "__main__":
    main()
