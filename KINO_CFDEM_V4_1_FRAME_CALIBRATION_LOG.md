# KinoCFDDEM v4.1 — Frame-by-frame calibration acquisition log

Updated: 2026-09-20

## Objective

Obtain real pixel frames from Lotería de Concepción draw recordings and feed
them into `kino_frame_calibration.py`. No thumbnail, login wall, generated
image or synthetic frame is accepted as a real draw frame.

## Calibrator contract

Current branch: `kinodem-cfdem-v4.1-video-calibration`

Frame calibrator commit lineage includes:
- `e0c385a1fdfad772de13b83f4831cd2e7f7d5a11`: initial frame-by-frame pipeline.
- `49333cff3664f5a5de6f5e4e73e0d57377022457`: temporal interval, source SHA-256 and block statistics.
- `e46b2a02f9fdbf0a567762443d6e2142fcde82c5`: CI contract workflow.

Verified contract:
- GitHub Actions run **35540886754**
- conclusion **success**
- tests cover temporal blocks and exact source hashing.

The pipeline outputs:
- `frame_measurements.csv`
- `block_measurements.csv`
- `frame_summary.json`
- `ratio_timeseries.png`
- annotated accepted frames
- contact sheet

Consecutive frames are explicitly treated as correlated observations.
The metrology summary therefore includes one-second temporal block statistics.

## Acquisition attempts

### 1. Selenium official YouTube embed
Run: **35538199381** — probe infrastructure succeeded.

Artifact:
- ID `10612658892`
- name `kino3279-youtube-selenium-probe`

Result:
- YouTube player reported duration about 3275 s.
- Captured screenshots contained the login/bot wall, not draw pixels.
- player response returned `LOGIN_REQUIRED`.
- `videoDetails`, `storyboards` and `streamingData` were unavailable.

Decision: rejected as calibration input.

### 2. YouTube storyboard endpoint
Run: **35540336190** — probe workflow succeeded.

Result:
- tested candidate storyboard mosaics on multiple official videos;
- storyboard URLs returned HTTP 403;
- static YouTube thumbnails remained accessible.

Decision: thumbnails may support static visual documentation but are not
accepted as frame-by-frame measurements.

### 3. Piped public frontends
Run: **35540412870** — retrieval failed.

Observed responses included HTTP 403/500, DNS failures and an upstream 526.

Decision: public Piped instances tested are not a reproducible source.

### 4. Invidious public frontends
Run: **35540491985** — retrieval failed.

Observed responses included HTTP 401/403.

Decision: public Invidious instances tested are not a reproducible source.

### 5. yt-dlp + BgUtils PO Token Provider
Run: **35540616432** — provider started successfully, media resolution failed.

Verified in verbose yt-dlp log:
- yt-dlp stable 2026.08.19;
- `bgutil:http-2.0.0` loaded as external PO Token Provider;
- Node 22 runtime available;
- `mweb` player response still returned `LOGIN_REQUIRED` before formats
  were made available.

The same probe was attempted against several official Kino video IDs and all
returned the same class of block.

Decision: the problem is upstream playability/IP reputation, not merely a
missing GVS PO token.

### 6. Alternate YouTube clients
Run: **35540736477** — probe workflow succeeded; every client failed to expose formats.

Clients tested:
- `web_safari`
- `web_embedded`
- `android_vr`
- `tv`
- `tv_simply`
- `ios`
- `android`

Most returned `LOGIN_REQUIRED`; `tv_simply` returned `UNPLAYABLE` with
the same bot-authentication reason.

Decision: no currently tested unauthenticated client on the GitHub-hosted
runner can supply real video pixels.

## Valid geometry evidence already available

The separate v4.1 static multi-view calibration remains valid:
- visual globe/ball diameter ratio: **12.55**
- combined sigma: **1.51262**
- 95% interval: **9.5853–15.5147**
- current surrogate ratio 12.5 is consistent with that interval
- absolute dimensional scale remains **not identified**

These results must not be described as a frame-by-frame temporal calibration.

## Acceptance criteria for the next video source

A candidate source is accepted only if:
1. decoded frames contain the actual draw scene;
2. source video identity/date can be traced;
3. SHA-256 is recorded before measurement;
4. frame rate and dimensions are recorded;
5. chamber/ball detections are visually auditable on annotated frames;
6. results are summarized by temporal blocks, not by naive frame count;
7. absolute millimetres remain unresolved until a real dimensional anchor is
   visible or independently documented.

## Next action

Continue looking for a non-YouTube-hosted or user-supplied copy of a draw video.
Once real pixels are available, run a coarse scan to locate the chamber-rich
interval, then process every frame of that interval with the validated
calibrator.


## 7. User-provided Kino 3281 screenshot calibration

Ten screenshots from draw 3281 (2026-09-18) were supplied directly by the user.
All ten source files are fingerprinted by SHA-256 in:

`calibration/kino3281_screenshot_calibration.json`

The fixed-camera geometry subset is:
- `10481.jpg`
- `10484.jpg`
- `10486.jpg`

Reference visible outer acrylic circle in `10481.jpg`:
- center: approximately (683.40, 382.20) px
- radius: approximately 282.84 px
- visible outer diameter: approximately 565.68 px

Clear-ball detector contract:
- yellow fill >= 0.90
- apparent radius 17-23 px
- normalized center radius <= 0.80 of the reference outer circle
- 15 accepted detections across the three fixed-camera images

Per-frame projected outer-shell diameter / apparent ball diameter:
- 10481: 13.8988
- 10484: 14.3210
- 10486: 14.6549

Equal-frame-weight median: **14.3210**.

This quantity is deliberately named `projected_outer_D_over_ball_d`.
It must **not** be substituted directly for the CFD fluid-domain diameter ratio:
the visible acrylic shell, perspective, ball depth and internal hardware all
affect the projection.

### Registration result and wall-motion consequence

ORB features in the non-yellow chamber annulus were registered against
`10481.jpg`.

- 10484: 636 RANSAC inliers; scale 1.0002425; translation about
  (-0.156, -0.157) px; median residual 0.127 px.
- 10486: 549 RANSAC inliers; scale 1.0000786; translation about
  (-0.184, -0.146) px; rotation about -0.0089 deg; median residual 0.267 px.

The screenshots therefore provide no support for the old whole-globe
`7 rad/s` wall-motion hypothesis. For v4.1 real-machine calibration that
hypothesis is **retired as the default**. The successfully validated rotating
case remains available only as a numerical surrogate/comparison case.

The images prove that ball positions change while the visible support/annulus
geometry stays registered, but they do **not** identify the driving mechanism.
Forced-air agitation is a plausible candidate from the machine appearance and
ball motion, but it remains unmeasured until video timing, airflow information,
or an identified machine specification is available.

### Reconciliation with the earlier 12.55 estimate

The earlier 12.55 value remains in the record as a broad static visual
surrogate estimate. The new 14.321 value explicitly uses the **visible outer
acrylic diameter** and therefore describes a different geometric quantity.
They must not be averaged together. A future video/physical calibration should
identify the inner usable fluid boundary separately from the outer acrylic
shell.

## 8. Kino 3281 archived-video recovery

The exact official video id for draw 3281 was resolved as `nf_0MJG9Aaw`.

Wayback snapshots dated 2026-09-19 preserve the YouTube player response.
Recovered metadata includes:
- duration about 3840.9 s;
- 1920x1080 at 60 fps;
- 1280x720 at 30 and 60 fps;
- 640x360 at 30 fps;
- 256x144 at 30 fps.

The archived player response also preserves the signed
`serverAbrStreamingUrl`, but the media object itself is not in Wayback:
an exact CDX lookup returned no capture and replay attempts returned HTTP 404.
Cobalt's fallback tried 18 candidate backends exhaustively and likewise
returned no valid YouTube content.

Therefore no temporal velocity result is claimed from the archived metadata.
