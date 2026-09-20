#!/usr/bin/env python3
from __future__ import annotations

import argparse
import functools
import http.server
import json
import math
import threading
import time
from pathlib import Path
from PIL import Image, ImageOps, ImageDraw

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
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


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass


def start_server(root: Path, port=8765):
    handler=functools.partial(QuietHandler,directory=str(root))
    server=http.server.ThreadingHTTPServer(("127.0.0.1",port),handler)
    th=threading.Thread(target=server.serve_forever,daemon=True)
    th.start()
    return server, f"http://127.0.0.1:{port}"


def player_duration(d):
    return float(d.execute_script("""
      let p=document.getElementById('movie_player');
      if (p && typeof p.getDuration==='function') {
        let z=p.getDuration(); if (isFinite(z) && z>0) return z;
      }
      let v=document.querySelector('video');
      if (v && isFinite(v.duration) && v.duration>0) return v.duration;
      return 0;
    """) or 0)


def current_time(d):
    return float(d.execute_script("""
      let p=document.getElementById('movie_player');
      if (p && typeof p.getCurrentTime==='function') return p.getCurrentTime()||0;
      let v=document.querySelector('video'); return v ? (v.currentTime||0) : 0;
    """) or 0)


def frame_body(d):
    try:
        return d.find_element(By.TAG_NAME,"body").text
    except Exception:
        return ""


def build_host_page(root: Path, base_url: str, video_id: str, host: str):
    src=(
        f"https://{host}/embed/{video_id}"
        f"?enablejsapi=1&origin={base_url}&autoplay=1&mute=1&controls=1&rel=0"
    )
    html=f"""<!doctype html>
<html>
<head>
  <meta name="referrer" content="strict-origin-when-cross-origin">
  <title>Kino frame calibration container</title>
</head>
<body style="margin:0;background:#111">
<iframe id="yt"
  width="1280" height="720"
  src="{src}"
  title="Official Kino video"
  frameborder="0"
  referrerpolicy="strict-origin-when-cross-origin"
  allow="autoplay; encrypted-media; picture-in-picture"
  allowfullscreen></iframe>
</body>
</html>"""
    (root/"index.html").write_text(html,encoding="utf-8")
    return src


def try_host(d, base_url, root, host, video_id, out):
    src=build_host_page(root,base_url,video_id,host)
    d.get(base_url+"/index.html")
    WebDriverWait(d,15).until(lambda x: x.find_elements(By.ID,"yt"))
    iframe=d.find_element(By.ID,"yt")
    # Parent diagnostic proves the player is in an enclosing page with a Referer.
    d.save_screenshot(str(out/f"parent_{host.replace('.','_')}.png"))
    d.switch_to.frame(iframe)
    WebDriverWait(d,20).until(lambda x:
        x.execute_script("return !!document.getElementById('movie_player') || !!document.querySelector('video')"))

    d.save_screenshot(str(out/f"frame_{host.replace('.','_')}.png"))
    (out/f"body_{host.replace('.','_')}.txt").write_text(
        frame_body(d),encoding="utf-8",errors="replace")

    d.execute_script("""
      let p=document.getElementById('movie_player');
      if (p) { try { p.mute(); p.playVideo(); } catch(e) {} }
      let v=document.querySelector('video');
      if (v) { v.muted=true; try { v.play(); } catch(e) {} }
    """)

    deadline=time.time()+35
    duration=0.0
    while time.time()<deadline:
        duration=player_duration(d)
        if duration>0:
            break
        time.sleep(0.5)
    if duration<=0:
        d.switch_to.default_content()
        return None

    d.execute_script("""
      let p=document.getElementById('movie_player');
      if (p) { try { p.pauseVideo(); } catch(e) {} }
      let v=document.querySelector('video'); if (v) v.pause();
    """)
    return {"embed_src":src,"duration":duration,"host":host}


def seek(d,t):
    d.execute_script("""
      let t=arguments[0];
      let p=document.getElementById('movie_player');
      if (p && typeof p.seekTo==='function') {
        try { p.mute(); p.seekTo(t,true); } catch(e) {}
      } else {
        let v=document.querySelector('video');
        if (v) { v.muted=true; v.currentTime=t; }
      }
    """,float(t))
    deadline=time.time()+8
    while time.time()<deadline:
        if abs(current_time(d)-t)<0.8:
            break
        time.sleep(0.1)
    time.sleep(0.45)
    d.execute_script("""
      let p=document.getElementById('movie_player');
      if (p) { try { p.pauseVideo(); } catch(e) {} }
      let v=document.querySelector('video'); if (v) v.pause();
    """)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--video-id",required=True)
    ap.add_argument("--outdir",default="youtube-probe")
    ap.add_argument("--n",type=int,default=36)
    args=ap.parse_args()
    out=Path(args.outdir); out.mkdir(parents=True,exist_ok=True)
    webroot=out/"webroot"; webroot.mkdir(exist_ok=True)
    server,base_url=start_server(webroot)

    d=make_driver()
    try:
        chosen=None
        for host in ("www.youtube.com","www.youtube-nocookie.com"):
            try:
                chosen=try_host(d,base_url,webroot,host,args.video_id,out)
            except Exception as exc:
                try: d.switch_to.default_content()
                except Exception: pass
                (out/f"error_{host.replace('.','_')}.txt").write_text(repr(exc),encoding="utf-8")
                chosen=None
            if chosen:
                break
        if not chosen:
            raise RuntimeError("No embedded host produced playable media; diagnostics saved")

        duration=float(chosen["duration"])
        times=[duration*i/(args.n-1) for i in range(args.n)] if args.n>1 else [0]
        rows=[]
        for i,t in enumerate(times):
            seek(d,t)
            player=d.find_element(By.ID,"movie_player")
            path=out/f"probe_{i:03d}_{t:08.3f}s.png"
            player.screenshot(str(path))
            rows.append({"index":i,"requested_s":t,"actual_s":current_time(d),"file":path.name})

        meta={
            "video_id":args.video_id,
            "host":chosen["host"],
            "container_url":base_url+"/index.html",
            "embed_src":chosen["embed_src"],
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

        print(json.dumps({
            "duration_s":duration,"captures":len(rows),
            "host":chosen["host"],"container_url":base_url+"/index.html"
        },indent=2))
    finally:
        d.quit()
        server.shutdown()
        server.server_close()


if __name__=="__main__":
    main()
