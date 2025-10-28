#!/usr/bin/env python3
"""
generate_candidates.py
- 入力: --email EMAIL
- 出力: candidates.txt (one URL per line)
説明:
- 種（seed）リストに既知の URL パターンを追加
- Bing / DuckDuckGo を試して web.archive.org や関連ドメインの候補を集める（ベストエフォート）
"""

import argparse
import re
import sys
from urllib.parse import quote_plus
import requests
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (compatible; ArchiveSearchBot/1.0; +https://example.com)"

SEEDS = [
    # 直接候補 — 必要に応じて追記してください
    "http://8028.teacup.com/koto/bbs",
    "http://www008.upp.so-net.ne.jp/NYMPH/",
    "http://www12.u-page.so-net.ne.jp:80/ka3/nymph-/main.html",
    "http://home.nifty.com/~cye04720/",
    "http://www.nifty.com/~cye04720/",
    # Wayback direct patterns (best-effort)
    "https://web.archive.org/web/*/*cye04720*",
    "https://web.archive.org/web/*/*cye04720@nifty.com*",
]

SEARCH_ENGINES = ["bing", "duckduckgo"]  # google はブロックされやすいため除外（必要なら追加）

def bing_search(query, max_results=50):
    url = "https://www.bing.com/search"
    params = {"q": query, "count": str(max_results)}
    headers = {"User-Agent": USER_AGENT}
    r = requests.get(url, params=params, headers=headers, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    links = []
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
        # DuckDuckGo html returns redirected 'uddg=' encoded links sometimes
        m = re.search(r"uddg=(https?%3A%2F%2F[^&]+)", href)
        if m:
            links.append(requests.utils.unquote(m.group(1)))
        elif href.startswith("http"):
            links.append(href)
    return links

def is_interesting(url, email):
    # web.archive.org、teacup、nifty、geocities などを優先
    patterns = ["web.archive.org", "teacup.com", "nifty.com", "geocities", "so-net.ne.jp", "upp.so-net"]
    return any(p in url for p in patterns) or email in url

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--email", required=True)
    p.add_argument("--out", default="candidates.txt")
    args = p.parse_args()
    email = args.email

    candidates = set(SEEDS)

    # search engines
    q = f"\"{email}\""
    try:
        print("[*] Bing search...")
        for u in bing_search(q, max_results=50):
            if is_interesting(u, email):
                candidates.add(u)
    except Exception as e:
        print("[!] Bing search failed:", e, file=sys.stderr)

    try:
        print("[*] DuckDuckGo search...")
        for u in ddg_search(q, max_results=50):
            if is_interesting(u, email):
                candidates.add(u)
    except Exception as e:
        print("[!] DuckDuckGo search failed:", e, file=sys.stderr)

    # normalize and write
    with open(args.out, "w", encoding="utf-8") as f:
        for u in sorted(candidates):
            f.write(u + "\n")

    print(f"[+] Wrote {len(candidates)} candidates to {args.out}")

if __name__ == "__main__":
    main()
