#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, math, time
from pathlib import Path
from PIL import Image, ImageOps, ImageDraw

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait


def driver():
    o=Options()
    o.add_argument("--headless=new")
    o.add_argument("--no-sandbox")
    o.add_argument("--disable-dev-shm-usage")
    o.add_argument("--disable-gpu")
    o.add_argument("--window-size=1280,900")
    o.add_argument("--autoplay-policy=no-user-gesture-required")
    o.add_argument("--mute-audio")
    o.add_argument("--lang=es-CL")
    return webdriver.Chrome(options=o)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--video-id",required=True)
    ap.add_argument("--outdir",default="youtube-probe")
    ap.add_argument("--n",type=int,default=36)
    args=ap.parse_args()
    out=Path(args.outdir); out.mkdir(parents=True,exist_ok=True)

    d=driver()
    try:
        url=f"https://www.youtube.com/embed/{args.video_id}?autoplay=1&mute=1&controls=1&rel=0"
        d.get(url)
        wait=WebDriverWait(d,30)
        wait.until(lambda x: x.execute_script("return !!document.querySelector('video')"))
        wait.until(lambda x: x.execute_script("let v=document.querySelector('video'); return v && isFinite(v.duration) && v.duration>0"))
        meta=d.execute_script("""
            let v=document.querySelector('video');
            return {duration:v.duration, width:v.videoWidth, height:v.videoHeight,
                    readyState:v.readyState, paused:v.paused, currentTime:v.currentTime};
        """)
        duration=float(meta["duration"])
        times=[duration*i/(args.n-1) for i in range(args.n)] if args.n>1 else [0]
        rows=[]
        for i,t in enumerate(times):
            d.execute_script("let v=document.querySelector('video'); v.pause(); v.currentTime=arguments[0];",float(t))
            wait.until(lambda x,tt=t: abs(float(x.execute_script("return document.querySelector('video').currentTime"))-tt)<0.5)
            time.sleep(0.35)
            v=d.find_element("tag name","video")
            p=out/f"probe_{i:03d}_{t:08.3f}s.png"
            v.screenshot(str(p))
            st=d.execute_script("""
                let v=document.querySelector('video');
                return {currentTime:v.currentTime,readyState:v.readyState,networkState:v.networkState,
                        width:v.videoWidth,height:v.videoHeight};
            """)
            rows.append({"index":i,"requested_s":t,"file":p.name,**st})

        (out/"probe_metadata.json").write_text(json.dumps({
            "video_id":args.video_id,"embed_url":url,"video":meta,"frames":rows
        },indent=2)+"\n",encoding="utf-8")

        # Contact sheet, with requested time label.
        imgs=[]
        for r in rows:
            im=Image.open(out/r["file"]).convert("RGB")
            thumb=ImageOps.contain(im,(400,240))
            tile=Image.new("RGB",(420,275),"white")
            tile.paste(thumb,((420-thumb.width)//2,5))
            dr=ImageDraw.Draw(tile)
            dr.text((10,250),f"{r['requested_s']:.2f} s",fill="black")
            imgs.append(tile)
        cols=3; rowsn=math.ceil(len(imgs)/cols)
        sheet=Image.new("RGB",(cols*420,rowsn*275),"white")
        for i,im in enumerate(imgs):
            sheet.paste(im,((i%cols)*420,(i//cols)*275))
        sheet.save(out/"contact_sheet.jpg",quality=90)
        print(json.dumps({"duration_s":duration,"captures":len(rows),"video_meta":meta},indent=2))
    finally:
        d.quit()


if __name__=="__main__":
    main()
