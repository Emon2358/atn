#!/usr/bin/env python3
"""
check_archives.py
- 入力:
    --email EMAIL
    --candidates candidates.txt
- 出力:
    found_archives.txt
動作:
- candidates.txt を読み、各 URL について:
  - もし web.archive.org のアーカイブ URL ならそのページを直接取得してメールを検索
  - それ以外は Wayback CDX API を使ってスナップショット一覧を取得、各スナップショットを取得してメールを検索
"""

import argparse
import re
import sys
import time
from urllib.parse import quote
import requests
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (compatible; ArchiveScan/1.0; +https://example.com)"
CDX_API_TEMPLATE = "https://web.archive.org/cdx/search/cdx?url={orig}&output=json&fl=timestamp,original&filter=statuscode:200&collapse=digest"

def fetch_text(url, timeout=30):
    headers = {"User-Agent": USER_AGENT}
    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.text

def search_in_html(text, email):
    # case-insensitive search
    return re.search(re.escape(email), text, re.IGNORECASE) is not None

def check_archive_url(url, email):
    try:
        text = fetch_text(url)
        if search_in_html(text, email):
            return True
    except Exception as e:
        print(f"[!] error fetching {url}: {e}", file=sys.stderr)
    return False

def query_cdx_and_scan(orig_url, email, found_set):
    orig_enc = quote(orig_url, safe="")
    api = CDX_API_TEMPLATE.format(orig=orig_enc)
    try:
        r = requests.get(api, headers={"User-Agent": USER_AGENT}, timeout=30)
        r.raise_for_status()
    except Exception as e:
        print(f"[!] CDX request failed for {orig_url}: {e}", file=sys.stderr)
        return

    try:
        data = r.json()
    except Exception:
        print(f"[!] CDX returned non-json for {orig_url}", file=sys.stderr)
        return

    if len(data) < 2:
        # no entries
        return

    # iterate snapshots
    for row in data[1:]:
        if not isinstance(row, list) or len(row) < 2:
            continue
        ts, original = row[0], row[1]
        snap = f"https://web.archive.org/web/{ts}id_/{original}"
        print(f"  Checking snapshot {snap} ...", flush=True)
        try:
            text = fetch_text(snap)
            if search_in_html(text, email):
                print(f"[+] FOUND in {snap}")
                found_set.add(snap)
            # be gentle with Wayback
            time.sleep(0.5)
        except Exception as e:
            print(f"[!] failed to fetch snapshot {snap}: {e}", file=sys.stderr)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--email", required=True)
    p.add_argument("--candidates", default="candidates.txt")
    p.add_argument("--out", default="found_archives.txt")
    args = p.parse_args()
    email = args.email

    # load candidates
    try:
        with open(args.candidates, "r", encoding="utf-8") as f:
            candidates = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print("[!] candidates file not found.", file=sys.stderr)
        sys.exit(1)

    found = set()

    for u in candidates:
        print(f"Processing candidate: {u}", flush=True)
        if "web.archive.org" in u:
            # direct archive URL (may be a wildcard pattern - handle simple case)
            if "*" in u:
                print("[*] Skipping wildcard archive pattern:", u)
                continue
            if check_archive_url(u, email):
                print(f"[+] FOUND: {u}")
                found.add(u)
        else:
            query_cdx_and_scan(u, email, found)

    # write results
    if found:
        with open(args.out, "w", encoding="utf-8") as f:
            for s in sorted(found):
                f.write(s + "\n")
        print(f"[+] Wrote {len(found)} found snapshots to {args.out}")
    else:
        print("[*] No matches found.")

if __name__ == "__main__":
    main()
