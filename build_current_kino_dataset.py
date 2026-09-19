#!/usr/bin/env python3
"""
KinoFM current dataset builder.
- #799..#2647: Kinoso SQLite, with known corrections.
- #2648..#3280: LoterAtor rendered with headless Chrome/Selenium.
- #3281 is excluded and reserved as external holdout.
"""
import argparse
import re
import time
import pandas as pd

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait

from kinofm_v4 import load_sqlite, validate_numbers

BASE="https://loterator.com/cl/kino/sorteos/"

def make_driver():
    o=Options()
    o.add_argument("--headless=new")
    o.add_argument("--no-sandbox")
    o.add_argument("--disable-dev-shm-usage")
    o.add_argument("--disable-gpu")
    o.add_argument("--window-size=1280,2200")
    o.add_argument("--lang=es-CL")
    return webdriver.Chrome(options=o)

def parse_body(text, min_draw, max_draw):
    # Rendered LoterAtor layout:
    # #3280
    # 16/09/2026
    # 1 2 5 ... 25
    pat=re.compile(
        r"#(\d+)\s+"
        r"(\d{2}/\d{2}/\d{4})\s+"
        r"((?:\d{1,2}\s+){13}\d{1,2})(?=\s|$)"
    )
    out={}
    for m in pat.finditer(text):
        d=int(m.group(1))
        if min_draw <= d <= max_draw:
            nums=[int(x) for x in m.group(3).split()]
            try:
                nums=validate_numbers(nums)
            except Exception:
                continue
            out[d]=(m.group(2),nums)
    return out

def scrape_loterator(min_draw=2648,max_draw=3280,max_pages=20):
    driver=make_driver()
    found={}
    try:
        for page in range(1,max_pages+1):
            url=BASE if page==1 else f"{BASE}?page={page}"
            driver.get(url)
            WebDriverWait(driver,20).until(
                lambda d: len(d.find_element("tag name","body").text) > 100
            )
            text=driver.find_element("tag name","body").text
            page_rows=parse_body(text,min_draw,max_draw)
            found.update(page_rows)
            draws=list(page_rows)
            print(f"selenium_page={page} parsed={len(draws)} captured={len(found)}")
            # Stop once this rendered page reaches/passes the target lower bound.
            all_nums=[int(x) for x in re.findall(r"#(\d+)",text)]
            if all_nums and min(all_nums) <= min_draw:
                break
            time.sleep(0.05)
    finally:
        driver.quit()

    missing=[d for d in range(min_draw,max_draw+1) if d not in found]
    if missing:
        raise RuntimeError(f"LoterAtor rendered history missing {len(missing)} draws: {missing[:50]}")

    rows=[]
    for d in range(min_draw,max_draw+1):
        fecha,nums=found[d]
        rows.append([d,fecha,*nums,BASE])
    return pd.DataFrame(rows,columns=["sorteo","fecha",*[f"n{i}" for i in range(1,15)],"fuente"])

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--sqlite",required=True)
    ap.add_argument("--out",default="kino_current_799_3280.csv")
    ap.add_argument("--max-pages",type=int,default=20)
    args=ap.parse_args()

    old=load_sqlite(args.sqlite)
    old["fuente"]="https://github.com/GioFranco79/kinoso"
    recent=scrape_loterator(max_pages=args.max_pages)

    merged=pd.concat([old,recent],ignore_index=True)
    merged["sorteo"]=pd.to_numeric(merged["sorteo"]).astype(int)
    merged=merged.sort_values("sorteo").drop_duplicates("sorteo",keep="last").reset_index(drop=True)

    expected=list(range(799,3281))
    got=merged["sorteo"].tolist()
    if got != expected:
        missing=sorted(set(expected)-set(got))
        extra=sorted(set(got)-set(expected))
        raise RuntimeError(f"Historical continuity failed. missing={missing[:30]} extra={extra[:30]}")

    for _,r in merged.iterrows():
        validate_numbers([r[f"n{i}"] for i in range(1,15)])

    merged.to_csv(args.out,index=False)
    print(f"OK: {len(merged)} continuous draws {merged.iloc[0].sorteo}..{merged.iloc[-1].sorteo}")
    print(f"RECENT_ROWS={len(recent)}")
    print(f"OUT={args.out}")

if __name__=="__main__":
    main()
