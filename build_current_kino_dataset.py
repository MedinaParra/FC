#!/usr/bin/env python3
"""
Construye un histórico continuo Kino Chile:
- #799..#2647 desde Sorteos.sqlite (Kinoso), con dos correcciones verificadas.
- #2648..#3280 desde ResultadosKinoChile (archivo HTML paginado + artículos).
- #3281 NO se incorpora: queda como holdout externo.

El script valida continuidad, 14 números únicos y rango 1..25.
"""
import argparse
import re
import time
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup

from kinofm_v4 import load_sqlite, validate_numbers

ARCHIVE = "https://www.resultadoskinochile.com/resultados-kino/"
UA = {"User-Agent":"Mozilla/5.0 KinoFM-research/0.6"}

def get(session, url, retries=4):
    last = None
    for k in range(retries):
        try:
            r = session.get(url, timeout=30, headers=UA)
            r.raise_for_status()
            return r
        except Exception as exc:
            last = exc
            time.sleep(0.5 * (k + 1))
    raise last

def collect_article_links(session, min_draw=2648, max_draw=3280, max_pages=140):
    links = {}
    for page in range(1, max_pages + 1):
        url = ARCHIVE if page == 1 else f"{ARCHIVE}page/{page}/"
        soup = BeautifulSoup(get(session, url).text, "html.parser")
        page_draws = []
        for a in soup.find_all("a", href=True):
            text = " ".join(a.stripped_strings)
            m = re.search(r"sorteo\s+(\d+)", text, flags=re.I)
            if not m:
                continue
            draw = int(m.group(1))
            href = urljoin(url, a["href"])
            page_draws.append(draw)
            if min_draw <= draw <= max_draw:
                links.setdefault(draw, href)
        print(f"archive_page={page} draws={len(set(page_draws))} captured={len(links)}")
        if page_draws and min(page_draws) <= min_draw:
            break
        time.sleep(0.03)

    missing = [d for d in range(min_draw, max_draw + 1) if d not in links]
    if missing:
        raise RuntimeError(f"Archivo sin links para {len(missing)} sorteos: {missing[:40]}")
    return links

def extract_main_kino(article_html):
    soup = BeautifulSoup(article_html, "html.parser")
    parts = list(soup.stripped_strings)

    # Buscar candidatos "Kino" cuyo segmento inmediatamente posterior contenga
    # exactamente una combinación válida antes de la siguiente categoría/heading.
    for idx, token in enumerate(parts):
        if token.strip().lower() != "kino":
            continue
        nums = []
        for s in parts[idx+1:idx+80]:
            # detener al entrar a tabla/categoría siguiente después de haber capturado números
            low = s.lower()
            if nums and ("nombre categoria" in low or "total categoría" in low or
                         "ganador" in low or "rekino" == low or "requete" in low):
                break
            if re.fullmatch(r"\d{1,2}", s):
                v = int(s)
                if 1 <= v <= 25:
                    nums.append(v)
                    if len(nums) == 14:
                        try:
                            return validate_numbers(nums)
                        except ValueError:
                            break
    raise ValueError("No se pudo extraer bloque Kino principal")

def scrape_recent(min_draw=2648, max_draw=3280, max_pages=140):
    session = requests.Session()
    links = collect_article_links(session, min_draw, max_draw, max_pages)
    rows = []
    failures = []
    for i, draw in enumerate(range(min_draw, max_draw + 1), start=1):
        url = links[draw]
        try:
            r = get(session, url)
            nums = extract_main_kino(r.text)
            # fecha: preferimos la fecha del título/URL solo como metadato; el sorteo manda.
            soup = BeautifulSoup(r.text, "html.parser")
            text = " ".join(soup.stripped_strings[:80])
            m = re.search(r"(\d{2}/\d{2}/\d{4})", text)
            fecha = m.group(1) if m else ""
            rows.append([draw, fecha, *nums, url])
        except Exception as exc:
            failures.append((draw, url, str(exc)))
        if i % 50 == 0 or i == (max_draw-min_draw+1):
            print(f"articles={i}/{max_draw-min_draw+1} ok={len(rows)} fail={len(failures)}")
        time.sleep(0.02)

    if failures:
        raise RuntimeError(f"Fallaron {len(failures)} artículos. Primeros: {failures[:15]}")

    return pd.DataFrame(
        rows,
        columns=["sorteo","fecha",*[f"n{i}" for i in range(1,15)],"fuente"]
    )

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sqlite", required=True)
    ap.add_argument("--out", default="kino_current_799_3280.csv")
    ap.add_argument("--max-pages", type=int, default=140)
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
    print(f"RECENT_ROWS={len(recent)}")
    print(f"OUT={args.out}")

if __name__ == "__main__":
    main()
