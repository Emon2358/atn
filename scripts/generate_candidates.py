#!/usr/bin/env python3
"""
generate_candidates.py
- usage:
    python scripts/generate_candidates.py --email cye04720@nifty.com --out candidates.txt
- Output: candidates.txt (one URL per line)
- Behavior:
  - Seed a set of likely host patterns (teacup, so-net, u-page, upp, geocities, nifty, etc.)
  - Query Bing and DuckDuckGo for the exact email and some related keywords to produce candidate pages
  - Keep only interesting URLs (web.archive.org, teacup, nifty, so-net, geocities, etc.)
  - Best-effort and conservative to reduce noise
"""

import argparse
import re
import sys
from urllib.parse import quote_plus
import requests
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (compatible; ArchiveSearch/1.0; +https://example.com)"
SEARCH_ENGINES = ["bing", "duckduckgo"]

# seed patterns / examples
SEEDS = [
    # explicit known pages you already mentioned
    "http://8028.teacup.com/koto/bbs",
    "http://www008.upp.so-net.ne.jp/NYMPH/",
    "http://www12.u-page.so-net.ne.jp:80/ka3/nymph-/main.html",
    "http://home.nifty.com/~cye04720/",
    "http://www.nifty.com/~cye04720/",
    # Wayback common patterns (informational)
    "https://web.archive.org/web/*/*cye04720*",
    "https://web.archive.org/web/*/*cye04720@nifty.com*",
]

# patterns to accept as "interesting"
INTEREST_PATTERNS = [
    "web.archive.org",
    "teacup.com",
    "nifty.com",
    "geocities",
    "so-net.ne.jp",
    "upp.so-net",
    "u-page.so-net",
]

def bing_search(query, max_results=50):
    url = "https://www.bing.com/search"
    params = {"q": query, "count": str(max_results)}
    headers = {"User-Agent": USER_AGENT}
    r = requests.get(url, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    links = []
    # Bing: results in li.b_algo h2 a
    for a in soup.select("li.b_algo h2 a[href]"):
        href = a.get("href")
        if href:
            links.append(href)
    return links

def ddg_search(query, max_results=50):
    url = "https://html.duckduckgo.com/html/"
    headers = {"User-Agent": USER_AGENT}
    data = {"q": query}
    r = requests.post(url, data=data, headers=headers, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    links = []
    for a in soup.select("a[href]"):
        href = a.get("href")
        if not href:
            continue
        # ddg returns redirect-like 'uddg=' sometimes
        m = re.search(r"uddg=(https?%3A%2F%2F[^&]+)", href)
        if m:
            links.append(requests.utils.unquote(m.group(1)))
        elif href.startswith("http"):
            links.append(href)
    return links

def is_interesting(url, email):
    if not url:
        return False
    lower = url.lower()
    if email.lower() in lower:
        return True
    for p in INTEREST_PATTERNS:
        if p in lower:
            return True
    return False

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--email", required=True)
    p.add_argument("--out", default="candidates.txt")
    args = p.parse_args()
    email = args.email.strip()

    candidates = set(SEEDS)

    # queries we will try (more than just exact email)
    queries = [
        f"\"{email}\"",
        f"\"{email.split('@')[0]}\"",
        f"\"{email}\" site:teacup.com",
        f"\"{email}\" site:archive.org",
        f"\"{email}\" site:nifty.com",
        f"\"{email.split('@')[0]}\" nifty",
        f"\"{email.split('@')[0]}\" nymph",
        f"\"{email}\" \"mailto:\"",
    ]

    for q in queries:
        try:
            print(f"[*] Bing search for: {q}", file=sys.stderr)
            for u in bing_search(q, max_results=50):
                if is_interesting(u, email):
                    candidates.add(u)
        except Exception as e:
            print(f"[!] Bing search failed for query {q}: {e}", file=sys.stderr)

        try:
            print(f"[*] DuckDuckGo search for: {q}", file=sys.stderr)
            for u in ddg_search(q, max_results=50):
                if is_interesting(u, email):
                    candidates.add(u)
        except Exception as e:
            print(f"[!] DuckDuckGo search failed for query {q}: {e}", file=sys.stderr)

    # final normalisation
    cleaned = set()
    for u in sorted(candidates):
        # strip parameters that are obviously noisy from search engine redirect wrappers
        cleaned.add(u.strip())

    with open(args.out, "w", encoding="utf-8") as f:
        for u in sorted(cleaned):
            f.write(u + "\n")

    print(f"[+] Wrote {len(cleaned)} candidates to {args.out}", file=sys.stderr)

if __name__ == "__main__":
    main()
