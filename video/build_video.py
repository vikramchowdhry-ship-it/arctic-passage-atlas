"""Assemble the explainer video from public-domain NASA/USGS/USCG imagery and a generated narration.

Run from the project root:  python video/build_video.py
All on-screen text and overlays (boxes, labels) are drawn by ffmpeg, so spelling is exact and nothing
is AI-generated imagery. Requires ffmpeg and ffprobe on PATH, plus Pillow.

Sources (all in video/assets, all public domain / NASA open data):
  NASA SVS sea-ice spiral and Goddard ice-retreat clip (Wikimedia Commons), USGS sea-ice photo and a
  U.S. Coast Guard icebreaker photo (Wikimedia Commons), plus NASA GIBS WMS images: Blue Marble, a
  Landsat WELD annual composite (c. 2000) and MODIS Terra true colour (2 Aug 2024 and 15 Jan 2024).
Backdrop music: an instrumental track generated with ElevenLabs (assets/backdrop_music.mp3).
"""

from __future__ import annotations

import math
import os
import subprocess
import sys
from pathlib import Path

import diagrams
from PIL import Image

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
# Intermediate files (frames, shots, screen captures) are large; keep them off the project drive.
_BIG_DRIVE = Path("E:/arctic-passage-atlas-video/work")
WORK = Path(os.environ.get("ATLAS_VIDEO_WORK") or (_BIG_DRIVE if Path("E:/").exists() else ROOT / "work"))
OUT = ROOT / "arctic-passage-atlas-explainer.mp4"
FONT = "C\\:/Windows/Fonts/segoeui.ttf"
FONT_BOLD = "C\\:/Windows/Fonts/segoeuib.ttf"
W, H, FPS = 1920, 1080, 30
CANVAS_W, CANVAS_H = 3200, 1800  # stills are drawn on this canvas, then eased down to 1080p
INTRO, OUTRO = 4.0, 4.0
XF = 0.5  # crossfade between shots, seconds
# `--reuse` keeps shots already rendered in video/work (delete one file to re-render just that shot).
REUSE = "--reuse" in sys.argv
CAPTIONS: dict[str, tuple[str | None, str]] = {}  # shot name -> (caption, footer line)
NOT_DATA = "Illustrative, not project data."
AMBER = "0xffb454"


def run(args: list[str]) -> None:
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], check=True)


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(out.stdout.strip())


def textfile(name: str, text: str) -> str:
    path = WORK / f"{name}.txt"
    path.write_text(text, encoding="utf-8")
    return path.as_posix().replace(":", "\\:")


def drawtext(name: str, text: str, size: int, y: str, bold: bool = False, color: str = "white",
             x: str = "(w-text_w)/2", box: bool = False) -> str:
    parts = [
        f"textfile='{textfile(name, text)}'",
        f"fontfile='{FONT_BOLD if bold else FONT}'",
        f"fontsize={size}", f"fontcolor={color}", f"x={x}", f"y={y}",
    ]
    if box:
        parts += ["box=1", "boxcolor=0x06121fCC", "boxborderw=22"]
    return "drawtext=" + ":".join(parts)


def card(name: str, lines: list[tuple[str, int, bool, str]], duration: float) -> Path:
    out = WORK / f"{name}.mp4"
    if REUSE and out.exists():
        return out
    y = 400
    filters = []
    for i, (text, size, bold, color) in enumerate(lines):
        filters.append(drawtext(f"{name}_{i}", text, size, str(y), bold, color))
        y += size + 40
    run([
        "-f", "lavfi", "-i", f"color=c=0x07182a:s={W}x{H}:r={FPS}:d={duration}",
        "-vf", ",".join(filters), "-pix_fmt", "yuv420p", "-an", str(out),
    ])
    return out


def caption_filters(name: str, caption: str | None, source: str, window: tuple[float, float]) -> list[str]:
    """Caption and source line for one shot, drawn only inside `window` (seconds on the final timeline).

    They are drawn after the crossfades so text from neighbouring shots never overprints."""
    enable = f"enable='between(t,{window[0]:.3f},{window[1]:.3f})'"
    filters = []
    if caption:
        lines = caption.split("|")
        for i, line in enumerate(lines):
            y = f"h-{250 - i * 95}" if len(lines) > 1 else "h-250"
            filters.append(drawtext(f"{name}_cap{i}", line, 54, y, bold=True, x="90", box=True) + f":{enable}")
    filters.append(
        drawtext(f"{name}_foot", source, 26, "h-46", color="0xcfe3f0", x="90") + f":{enable}"
    )
    return filters


def outline(x: int, y: int, w: int, h: int, thickness: int = 10, color: str = AMBER) -> str:
    return f"drawbox=x={x}:y={y}:w={w}:h={h}:color={color}@1:t={thickness}"


def label(name: str, text: str, x: int, y: int, size: int = 78) -> str:
    return drawtext(name, text, size, str(y), bold=True, x=str(x), box=True)


def smootherstep(t: float) -> float:
    return t * t * t * (t * (6 * t - 15) + 10)


def still(name: str, src: str, duration: float, caption: str | None, source: str,
          note: str = NOT_DATA, overlays: list[str] | None = None, focus: tuple[float, float] = (0.5, 0.5),
          zoom: tuple[float, float] = (1.0, 1.15)) -> Path:
    """Slow, eased push-in (or pull-out) over a 16:9-cropped still.

    `overlays` are drawn in canvas pixels (3200x1800) before the move, so boxes and labels stay locked
    to the ground. Every frame is resampled with Lanczos from a floating-point crop box, so motion is
    sub-pixel smooth. Zoom is interpolated in log space and eased, so it starts and ends gently, and
    the crop centre travels from the first frame's centre to the last frame's in step with the zoom.
    """
    out = WORK / f"{name}.mp4"
    CAPTIONS[name] = (caption, f"{source}. {note}")
    if REUSE and out.exists():
        return out
    canvas_path = WORK / f"{name}_canvas.png"
    prep = f"scale={CANVAS_W}:{CANVAS_H}:force_original_aspect_ratio=increase,crop={CANVAS_W}:{CANVAS_H}"
    run(["-i", str(ASSETS / src), "-vf", ",".join([prep, *(overlays or [])]), "-frames:v", "1",
         str(canvas_path)])
    canvas = Image.open(canvas_path).convert("RGB")

    def centre_at(z: float) -> tuple[float, float]:
        """Crop centre for zoom z: the focus point, pulled inside the image where the crop needs it."""
        bw, bh = CANVAS_W / z, CANVAS_H / z
        cx = min(max(focus[0] * CANVAS_W, bw / 2), CANVAS_W - bw / 2)
        cy = min(max(focus[1] * CANVAS_H, bh / 2), CANVAS_H - bh / 2)
        return cx, cy

    z0, z1 = zoom
    c0, c1 = centre_at(z0), centre_at(z1)
    frames = max(2, round(duration * FPS))
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
         "-pix_fmt", "yuv420p", "-an", str(out)],
        stdin=subprocess.PIPE,
    )
    assert proc.stdin is not None
    for i in range(frames):
        e = smootherstep(i / (frames - 1))
        z = math.exp(math.log(z0) + (math.log(z1) - math.log(z0)) * e)
        bw, bh = CANVAS_W / z, CANVAS_H / z
        cx = c0[0] + (c1[0] - c0[0]) * e
        cy = c0[1] + (c1[1] - c0[1]) * e
        x0 = min(max(cx - bw / 2, 0), CANVAS_W - bw)
        y0 = min(max(cy - bh / 2, 0), CANVAS_H - bh)
        frame = canvas.resize((W, H), Image.LANCZOS, box=(x0, y0, x0 + bw, y0 + bh))
        proc.stdin.write(frame.tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed while encoding {name}")
    return out


def diagram(name: str, draw, duration: float, caption: str | None, footer: str) -> Path:
    """A schematic shot drawn frame by frame by video/diagrams.py."""
    out = WORK / f"{name}.mp4"
    CAPTIONS[name] = (caption, footer)
    if REUSE and out.exists():
        return out
    frames = max(2, round(duration * FPS))
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-pix_fmt", "yuv420p", "-an", str(out)],
        stdin=subprocess.PIPE,
    )
    assert proc.stdin is not None
    for i in range(frames):
        proc.stdin.write(draw(i / FPS, duration).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg failed while encoding {name}")
    return out


def clip(name: str, src: str, start: float, duration: float, caption: str | None, source: str,
         square: bool = False, note: str = NOT_DATA) -> Path:
    out = WORK / f"{name}.mp4"
    CAPTIONS[name] = (caption, f"{source}. {note}")
    if REUSE and out.exists():
        return out
    if square:
        # Square visualisation: blurred copy fills the frame, sharp copy sits in the middle.
        graph = (
            f"[0:v]split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
            f"boxblur=30:5,eq=brightness=-0.15[bg];[b]scale=-2:{H}[fg];[bg][fg]overlay=(W-w)/2:0[v0]"
        )
    else:
        graph = f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}[v0]"
    run([
        "-ss", f"{start}", "-t", f"{duration}", "-i", str(ASSETS / src),
        "-filter_complex", f"{graph};[v0]fps={FPS}[v]", "-map", "[v]",
        "-pix_fmt", "yuv420p", "-an", str(out),
    ])
    return out


# Pixel positions on the downloaded NASA GIBS images, computed from the project's configured
# bounding box (configs/cambridge-bay.json) and the hamlet coordinates in aoi.shore_reference_point.
# Landsat image: 2560x1440 covering lon -106.7..-103.5, lat 68.83..69.47 (scale 1.25 to the canvas).
LANDSAT_SCALE = CANVAS_W / 2560
AOI_L = (840, 270, 880, 900)  # x, y, w, h on the 2560x1440 image
TOWN_L = (1318, 801)
# MODIS image (EPSG:3413, 1920x1080) AOI marker, centre (962, 535), canvas scale 3200/1920.
MODIS_SCALE = CANVAS_W / 1920
AOI_M_CENTRE = (962, 535)


def main() -> None:
    WORK.mkdir(exist_ok=True)
    narration = ASSETS / "narration.wav"
    narr = probe_duration(narration)

    # Scene boundaries (seconds into the narration) come from a transcription of the final recording.
    b = [0.0, 7.0, 11.4, 14.0, 17.6, 22.6, 25.9, 31.0, 35.0, 39.0, 43.5, 46.6, 49.8, 53.0, narr]
    d = [b[k + 1] - b[k] for k in range(len(b) - 1)]

    s = LANDSAT_SCALE
    ax, ay, aw, ah = (round(v * s) for v in AOI_L)
    tx, ty = round(TOWN_L[0] * s), round(TOWN_L[1] * s)
    landsat_overlays = [
        outline(ax, ay, aw, ah),
        label("lbl_aoi", "Study area  43.9 x 44.5 km", ax, ay - 130, 70),
        outline(tx - 22, ty - 22, 44, 44, 8, "white"),
        label("lbl_town", "Cambridge Bay", tx + 50, ty - 40, 60),
    ]
    town = (tx / CANVAS_W, ty / CANVAS_H)

    m = MODIS_SCALE
    mx, my = round(AOI_M_CENTRE[0] * m), round(AOI_M_CENTRE[1] * m)
    modis_overlays = [
        outline(mx - 90, my - 90, 180, 180, 10),
        label("lbl_modis", "Study area", mx + 120, my - 40, 70),
    ]
    marker = (AOI_M_CENTRE[0] / W, AOI_M_CENTRE[1] / H)

    def length(i: int) -> float:
        """Each shot is rendered XF seconds long so it can dissolve into the next without moving cuts."""
        return d[i] + XF

    # (path, seconds the shot owns on the timeline)
    specs: list[tuple[Path, float]] = [
        (card("title", [
            ("Arctic Passage Atlas", 96, True, "white"),
            ("A project by Maheep Chowdhary", 52, False, "0x9fd8ee"),
        ], INTRO + XF), INTRO),
        (clip("s1", "sea_ice_spiral.webm", 0, length(0), None, "NASA Scientific Visualization Studio",
              square=True), d[0]),
        # Top-left crop on purpose: keeps the ship in this photo out of frame.
        (still("s2", "arctic_intersection.jpg", length(1), "Developed by Maheep Chowdhary", "USGS",
               focus=(0.25, 0.22), zoom=(1.45, 1.65)), d[1]),
        # Regional NASA Blue Marble view that pushes in on the study area (same GIBS frame as the MODIS shots).
        (still("s3", "p_blue_marble_wide.jpg", d[2] + d[3] + XF, "Study area: Cambridge Bay, Nunavut",
               "NASA Blue Marble, via NASA GIBS", overlays=modis_overlays, focus=marker,
               zoom=(1.0, 2.6)), d[2] + d[3]),
        (still("s4", "landsat_aoi_2000.jpg", length(4), "Layer 1: surface change (Landsat)",
               "NASA/USGS Landsat composite, c. 2000, via NASA GIBS",
               overlays=landsat_overlays, focus=town, zoom=(1.0, 1.8)), d[4]),
        (still("s5", "p_modis_winter.jpg", length(5), "January: polar night, no optical image",
               "NASA MODIS Terra, 15 Jan 2024, via NASA GIBS", overlays=modis_overlays,
               focus=marker, zoom=(1.0, 1.25)), d[5]),
        (clip("s6", "ice_retreat_2013.ogv", 8, length(6), "Layer 2: sea ice (Sentinel-1 radar)",
              "NASA Goddard Space Flight Center"), d[6]),
        # The only shot with a ship in it.
        (still("s7", "icebreakers_1.jpg", length(7), "Layer 3: vessel events (Global Fishing Watch)",
               "U.S. Coast Guard", zoom=(1.18, 1.0)), d[7]),
        (still("s8", "gibs_modis_2024-07-22.jpg", length(8), "Ice, land and shipping: one study area",
               "NASA MODIS, 22 Jul 2024, via NASA GIBS", focus=(0.58, 0.6), zoom=(1.0, 1.45)), d[8]),
        # Concept graphics: they illustrate what the narrator says instead of showing more ice.
        (diagram("s9", diagrams.draw_limits, length(9), "Reports what the data show, and its limits",
                 "Schematic. Limits are listed in docs/METHODOLOGY.md."), d[9]),
        (diagram("s10", diagrams.draw_gap, length(10), "A signal gap is not suspicious.",
                 "Schematic, not data. The project defines a gap as 12 hours or more."), d[10]),
        (diagram("s11", diagrams.draw_pixel, length(11), "A changed pixel is not confirmed construction.",
                 "Schematic, not data."), d[11]),
        (diagram("s12", diagrams.draw_terminal, length(12), "Every result is reproducible from open code",
                 "Real output of the project's verify command (demonstration data)."), d[12]),
        (diagram("s13", diagrams.draw_credits, length(13), None,
                 "Credits. The narrator reads the same sources aloud."), d[13]),
        (card("outro", [
            ("Open source and reproducible", 64, True, "white"),
            ("A project by Maheep Chowdhary", 40, False, "0x9fd8ee"),
            ("Demonstration data. Not an operational or surveillance system.", 34, False, "0xcfe3f0"),
        ], OUTRO), OUTRO),
    ]

    total = INTRO + narr + OUTRO
    n = len(specs)
    inputs: list[str] = []
    for path, _ in specs:
        inputs += ["-i", str(path)]
    inputs += ["-i", str(narration)]
    narration_idx = n

    # Crossfade chain: each dissolve of XF seconds starts where the previous shot's own time ends.
    chain: list[str] = []
    label_in, elapsed = "[0:v]", 0.0
    for k in range(1, n):
        elapsed += specs[k - 1][1]
        out_label = f"[x{k}]"
        chain.append(
            f"{label_in}[{k}:v]xfade=transition=fade:duration={XF}:offset={elapsed:.3f}{out_label}"
        )
        label_in = out_label
    # A shot is fully on screen from the end of the dissolve into it until the dissolve out of it begins.
    texts: list[str] = []
    start = 0.0
    for path, own in specs:
        if path.stem in CAPTIONS:
            texts += caption_filters(path.stem, *CAPTIONS[path.stem], window=(start + XF, start + own))
        start += own
    chain.append(
        f"{label_in}{','.join(texts + [''])}fade=t=in:st=0:d=0.8,fade=t=out:st={total - 1.0:.2f}:d=1.0,"
        f"format=yuv420p[v]"
    )

    delay = int(INTRO * 1000)
    music = ASSETS / "backdrop_music.mp3"
    voice = (f"[{narration_idx}:a]adelay={delay}|{delay},loudnorm=I=-16:TP=-1.5:LRA=11,"
             f"apad=whole_dur={total}")
    if music.exists():
        # Backdrop music (ElevenLabs, instrumental) sits about 8-12 dB under the voice and ducks gently
        # (ratio 2) while the narrator speaks; heavier ducking made it inaudible, since the voice-over
        # runs the whole video; it fades in over 2 s and out over the last 4 s. The track's own first 3 s
        # are near-silent, so playback starts 3 s in.
        inputs += ["-i", str(music)]
        music_idx = narration_idx + 1
        audio = (
            f"{voice},asplit=2[v1][v2];"
            f"[{music_idx}:a]atrim=start=3:end={3 + total:.2f},asetpts=PTS-STARTPTS,volume=0.55,"
            f"afade=t=in:st=0:d=2,afade=t=out:st={total - 4:.2f}:d=4,apad=whole_dur={total}[m];"
            f"[m][v1]sidechaincompress=threshold=0.12:ratio=2:attack=50:release=800:makeup=1[duck];"
            f"[duck][v2]amix=inputs=2:normalize=0:duration=longest[a]"
        )
    else:
        audio = f"{voice}[a]"
    run([
        *inputs, "-filter_complex", ";".join([*chain, audio]),
        "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        # modest memory use: the 15-input crossfade graph is heavy on a small machine
        "-threads", "2", "-filter_complex_threads", "1", "-x264-params", "rc-lookahead=10:ref=2",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-t", f"{total}", str(OUT),
    ])
    print(f"Wrote {OUT} ({probe_duration(OUT):.1f} s)")


if __name__ == "__main__":
    main()
