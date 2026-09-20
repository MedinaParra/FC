#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, math, time
from pathlib import Path
from PIL import Image, ImageOps, ImageDraw

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait


def make_driver():
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


def player_duration(d):
    return d.execute_script("""
      let p=document.getElementById('movie_player');
      if (p && typeof p.getDuration==='function') {
        let z=p.getDuration(); if (isFinite(z) && z>0) return z;
      }
      let v=document.querySelector('video');
      if (v && isFinite(v.duration) && v.duration>0) return v.duration;
      return 0;
    """)


def current_time(d):
    return float(d.execute_script("""
      let p=document.getElementById('movie_player');
      if (p && typeof p.getCurrentTime==='function') return p.getCurrentTime()||0;
      let v=document.querySelector('video'); return v ? (v.currentTime||0) : 0;
    """))


def try_host(d, host, video_id, out):
    url=f"https://{host}/embed/{video_id}?autoplay=1&mute=1&controls=1&rel=0"
    d.get(url)
    WebDriverWait(d,20).until(lambda x:
        x.execute_script("return !!document.getElementById('movie_player') || !!document.querySelector('video')"))

    # Always preserve diagnostics before deciding whether playback works.
    d.save_screenshot(str(out/f"page_{host.replace('.','_')}.png"))
    (out/f"body_{host.replace('.','_')}.txt").write_text(
        d.find_element("tag name","body").text,encoding="utf-8",errors="replace")

    # Trigger muted playback through both APIs.
    d.execute_script("""
      let p=document.getElementById('movie_player');
      if (p) { try { p.mute(); p.playVideo(); } catch(e) {} }
      let v=document.querySelector('video');
      if (v) { v.muted=true; try { v.play(); } catch(e) {} }
    """)
    deadline=time.time()+30
    duration=0
    while time.time()<deadline:
        duration=float(player_duration(d) or 0)
        if duration>0:
            break
        time.sleep(0.5)
    if duration<=0:
        return None

    # Pause after media metadata becomes available.
    d.execute_script("""
      let p=document.getElementById('movie_player');
      if (p) { try { p.pauseVideo(); } catch(e) {} }
      let v=document.querySelector('video'); if (v) v.pause();
    """)
    return {"url":url,"duration":duration}


def seek(d,t):
    d.execute_script("""
      let t=arguments[0];
      let p=document.getElementById('movie_player');
      if (p && typeof p.seekTo==='function') {
        try { p.mute(); p.seekTo(t,true); } catch(e) {}
      } else {
        let v=document.querySelector('video'); if (v) { v.muted=true; v.currentTime=t; }
      }
    """,float(t))
    deadline=time.time()+8
    while time.time()<deadline:
        if abs(current_time(d)-t)<0.8:
            break
        time.sleep(0.1)
    time.sleep(0.4)
    d.execute_script("""
      let p=document.getElementById('movie_player'); if (p) { try { p.pauseVideo(); } catch(e) {} }
      let v=document.querySelector('video'); if (v) v.pause();
    """)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--video-id",required=True)
    ap.add_argument("--outdir",default="youtube-probe")
    ap.add_argument("--n",type=int,default=36)
    args=ap.parse_args()
    out=Path(args.outdir); out.mkdir(parents=True,exist_ok=True)

    d=make_driver()
    try:
        chosen=None
        for host in ("www.youtube-nocookie.com","www.youtube.com"):
            try:
                chosen=try_host(d,host,args.video_id,out)
            except Exception as exc:
                (out/f"error_{host.replace('.','_')}.txt").write_text(repr(exc),encoding="utf-8")
                chosen=None
            if chosen:
                chosen["host"]=host
                break
        if not chosen:
            raise RuntimeError("No public embed host produced a playable duration; diagnostics saved")

        duration=float(chosen["duration"])
        times=[duration*i/(args.n-1) for i in range(args.n)] if args.n>1 else [0]
        rows=[]
        for i,t in enumerate(times):
            seek(d,t)
            p=d.find_element("id","movie_player")
            path=out/f"probe_{i:03d}_{t:08.3f}s.png"
            p.screenshot(str(path))
            rows.append({
                "index":i,"requested_s":t,"actual_s":current_time(d),"file":path.name
            })

        meta={
            "video_id":args.video_id,
            "host":chosen["host"],
            "embed_url":chosen["url"],
            "duration_s":duration,
            "frames":rows
        }
        (out/"probe_metadata.json").write_text(json.dumps(meta,indent=2)+"\n",encoding="utf-8")

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
        print(json.dumps({"duration_s":duration,"captures":len(rows),"host":chosen["host"]},indent=2))
    finally:
        d.quit()


if __name__=="__main__":
    main()
