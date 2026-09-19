#!/usr/bin/env python3
"""
Construye un histórico continuo Kino Chile:
- #799..#2647 desde Sorteos.sqlite (Kinoso), con dos correcciones verificadas.
- #2648..#3280 desde el historial público paginado de LoterAtor.
- #3281 NO se incorpora: queda como holdout externo.
"""
import argparse
import re
import time
from pathlib import Path

import pandas as pd
import requests
from bs4 import BeautifulSoup

from kinofm_v4 import load_sqlite, validate_numbers

BASE = "https://loterator.com/cl/kino/sorteos/"

def scrape_recent(min_draw=2648, max_draw=3280, max_pages=20, delay=0.15):
    found = {}
    for page in range(1, max_pages + 1):
        url = BASE if page == 1 else f"{BASE}?page={page}"
        r = requests.get(url, timeout=30, headers={"User-Agent":"KinoFM-research/0.5"})
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        parts = list(soup.stripped_strings)
        page_draws = []
        i = 0
        while i < len(parts):
            if re.fullmatch(r"#\d+", parts[i]):
                draw = int(parts[i][1:])
                if i + 2 < len(parts) and re.fullmatch(r"\d{2}/\d{2}/\d{4}", parts[i+1]):
                    nums = [int(x) for x in parts[i+2].split() if x.isdigit()]
                    if len(nums) == 14:
                        nums = validate_numbers(nums)
                        page_draws.append((draw, parts[i+1], nums, url))
                        if min_draw <= draw <= max_draw:
                            found[draw] = (parts[i+1], nums, url)
                        i += 3
                        continue
            i += 1
        print(f"page={page} parsed={len(page_draws)} captured_total={len(found)}")
        if page_draws and min(d for d, *_ in page_draws) <= min_draw:
            break
        time.sleep(delay)
    missing = [d for d in range(min_draw, max_draw + 1) if d not in found]
    if missing:
        raise RuntimeError(f"Faltan sorteos recientes ({len(missing)}): {missing[:30]}")
    rows = []
    for d in range(min_draw, max_draw + 1):
        fecha, nums, src = found[d]
        rows.append([d, fecha, *nums, src])
    return pd.DataFrame(rows, columns=["sorteo","fecha",*[f"n{i}" for i in range(1,15)],"fuente"])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite", required=True)
    ap.add_argument("--out", default="kino_current_799_3280.csv")
    ap.add_argument("--max-pages", type=int, default=20)
    args = ap.parse_args()

    old = load_sqlite(args.sqlite)
    old["fuente"] = "https://github.com/GioFranco79/kinoso"
    recent = scrape_recent(max_pages=args.max_pages)

    merged = pd.concat([old, recent], ignore_index=True)
    merged["sorteo"] = pd.to_numeric(merged["sorteo"]).astype(int)
    merged = merged.sort_values("sorteo").drop_duplicates("sorteo", keep="last").reset_index(drop=True)

    expected = list(range(799, 3281))
    got = merged["sorteo"].tolist()
    if got != expected:
        missing = sorted(set(expected) - set(got))
        extra = sorted(set(got) - set(expected))
        raise RuntimeError(f"Histórico no continuo. missing={missing[:20]} extra={extra[:20]}")

    for _, r in merged.iterrows():
        validate_numbers([r[f"n{i}"] for i in range(1,15)])

    merged.to_csv(args.out, index=False)
    print(f"OK: {len(merged)} sorteos continuos {merged.iloc[0].sorteo}..{merged.iloc[-1].sorteo}")
    print(f"OUT={args.out}")

if __name__ == "__main__":
    main()
