"""Builds five 30-second vertical reels (1080x1920) for the Arctic Passage Atlas Instagram account.

Narration is generated text-to-speech (Higgsfield, voice Arthur); the motion clips marked "AI-generated footage"
come from a text-to-video model; the data imagery is NASA, USGS and U.S. Coast Guard public-domain material from
video/assets. All on-screen text is drawn by ffmpeg so spelling is exact. Requires ffmpeg and ffprobe on PATH.

    python video/build_reels.py [reel numbers...]        # default: all five

Inputs live in WORK/raw (voiceN.wav, clipN.mp4) and WORK/shots; outputs go to WORK/out. WORK is on E:.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"
WORK = Path("E:/atlas-reels")
RAW, SHOTS, OUT, TMP = WORK / "raw", WORK / "shots", WORK / "out", WORK / "tmp"
W, H, FPS = 1080, 1920, 30
TOTAL = 30.0
FONT_BOLD = "C\\:/Windows/Fonts/segoeuib.ttf"
FONT = "C\\:/Windows/Fonts/segoeui.ttf"
URL = "arcticpassageatlas.com"

AI = "AI-generated footage"
NASA_GIBS = "NASA GIBS"
LANDSAT = "NASA/USGS Landsat via NASA GIBS"

# Each segment: (kind, source, narrated text for its share of the timeline, on-screen caption, credit).
# kind: clip (generated mp4), still (jpg/png with slow push-in), video (existing footage), card (end card).
REELS: dict[int, list[tuple[str, str, str, str, str]]] = {
    1: [
        ("clip", "clip0.mp4", "This is the Arctic. It is warming much faster than the rest of the planet.",
         "This is the Arctic.\nIt is warming fast.", AI),
        ("video", "ice_retreat_2013.ogv", "As summer sea ice shrinks, routes that were frozen shut for centuries are starting to open.",
         "Summer sea ice is shrinking.", "NASA Goddard Space Flight Center"),
        ("still", "p_blue_marble_wide.jpg", "The Northwest Passage. The Northern Sea Route.",
         "Northwest Passage\nNorthern Sea Route", "NASA Blue Marble via NASA GIBS"),
        ("clip", "clip3.mp4", "On paper, they can cut thousands of kilometres between Asia and Europe.",
         "On paper: thousands of km\nshorter than the Suez route", AI),
        ("still", "icebreakers_1.jpg", "But who is actually watching them? I built a free, open map to find out.",
         "Who is watching?\nI built a free open map.", "U.S. Coast Guard"),
        ("card", "", "Follow for one Arctic story, every day.", "One Arctic story\nevery day", ""),
    ],
    2: [
        ("clip", "clip1.mp4", "Here is a word you probably do not know: geomatics.", "GEOMATICS", AI),
        ("clip", "clip2.mp4", "It is the science of measuring, mapping, and understanding places, using satellites, GPS, and data.",
         "Measuring and mapping places\nwith satellites, GPS and data", AI),
        ("still", "landsat_aoi_1990.jpg", "Landsat satellites have photographed Earth since nineteen seventy two, and the archive has been free to use since two thousand eight.",
         "Landsat: images since 1972\nFree archive since 2008", LANDSAT),
        ("still", "landsat_aoi_2000.jpg", "That means anyone can compare the same Arctic shoreline across fifty years.",
         "The same Arctic coast,\ncompared across decades", LANDSAT),
        ("card", "", "I am studying geomatics at Waterloo, and this is what I do with it. Follow for more.",
         "Studying geomatics\nat Waterloo", ""),
    ],
    3: [
        ("still", "icebreakers_2.jpg", "Ships do not sail in straight lines. They go around land, ice, and shallow water.",
         "Ships do not sail\nin straight lines.", "U.S. Coast Guard"),
        ("still", "arctic_intersection.jpg", "So how do you plan a route across the Arctic?",
         "How do you plan\nan Arctic route?", "USGS"),
        ("clip", "clip5.mp4", "You turn the ocean into a grid, mark every cell as water or blocked, and let an algorithm search for the shortest clear path.",
         "Ocean to grid.\nWater or blocked.\nSearch the shortest path.", AI),
        ("shot", "route_c.png", "My route planner does exactly that, for the Arctic and the whole world.",
         "Arctic and worldwide\nroute planner", ""),
        ("card", "", "It is a learning tool, not for navigation. Try it free at arctic passage atlas dot com.",
         "A learning tool.\nNot for navigation.", ""),
    ],
    4: [
        ("clip", "clip4.mp4", "In the Arctic winter, the sun does not rise for weeks.",
         "Arctic winter:\nweeks without sun", AI),
        ("still", "p_modis_winter.jpg", "So how do satellites see the ice? Radar.",
         "How do satellites\nsee the ice?\nRadar.", "NASA MODIS via NASA GIBS"),
        ("clip", "clip7.mp4", "Sentinel one sends its own microwave pulses through darkness and clouds, and listens for what bounces back.",
         "Sentinel-1 sends its own\nmicrowave pulses", AI),
        ("video", "sea_ice_spiral.webm", "Calm water and ice scatter radar very differently. Turn that into a map, and you can watch the sea freeze, from space, in the dark.",
         "Sea ice, watched\nfrom space", "NASA Scientific Visualization Studio"),
        ("card", "", "Pretty incredible. More tomorrow.", "More tomorrow", ""),
    ],
    5: [
        ("clip", "clip6.mp4", "Right now, a weather station in Cambridge Bay, Nunavut, is reporting the temperature.",
         "Live weather from\nCambridge Bay, Nunavut", AI),
        ("still", "gibs_modis_2024-08-02.jpg", "Ships are broadcasting their positions. Satellites pass overhead every day.",
         "Ships broadcast positions.\nSatellites pass daily.", "NASA MODIS via NASA GIBS"),
        ("shot", "live_c.png", "All of it is public data, and I pulled it into one live map.",
         "Public data.\nOne live map.", ""),
        ("still", "gibs_modis_2024-07-22.jpg", "One honest warning: a missing ship on the map does not mean a missing ship. Coverage in the Arctic is thin.",
         "A missing dot is not\na missing ship.", "NASA MODIS via NASA GIBS"),
        ("card", "", "See it live at arctic passage atlas dot com.", "See it live", ""),
    ],
    6: [
        ("clip", "clip1.mp4", "Cambridge Bay, Nunavut. A town of under two thousand people, on the Northwest Passage.",
         "Cambridge Bay, Nunavut", AI),
        ("still", "landsat_aoi_2000.jpg", "Its Inuinnaqtun name, Iqaluktuuttiaq, means good fishing place.",
         "Iqaluktuuttiaq:\n\"good fishing place\"", LANDSAT),
        ("still", "p_blue_marble_wide.jpg", "Canada's High Arctic Research Station opened here in twenty nineteen.",
         "Canada's High Arctic\nResearch Station, since 2019", "NASA Blue Marble via NASA GIBS"),
        ("clip", "clip6.mp4", "It is also the study area for my project: a forty four kilometre box of tundra, coast and sea ice.",
         "The study area:\na 44 km box", AI),
        ("still", "gibs_modis_2024-08-02.jpg", "A small place on a big route is a good place to test a method.",
         "A small place on a big route", "NASA MODIS via NASA GIBS"),
        ("card", "", "Follow for more.", "Follow for more", ""),
    ],
    7: [
        ("still", "landsat_aoi_2000.jpg", "My first map flagged about seven hundred changes in the Arctic. I almost believed it.",
         "My first run flagged\n~700 \"changes\"", LANDSAT + " (illustration)"),
        ("still", "gibs_modis_2024-08-12.jpg", "Then I looked closer: many looked like old patches of snow, bright in one year and gone in the next.",
         "Many looked like\nold snow patches", "NASA MODIS via NASA GIBS (illustration)"),
        ("still", "landsat_aoi_1990.jpg", "So I masked snow, skipped very bright pixels, and made every change show up in two separate pairs of years.",
         "Mask snow. Skip bright pixels.\nRequire two year-pairs.", "NASA/USGS Landsat"),
        ("clip", "clip7.mp4", "Seven hundred became forty two. And even those are only candidates, not confirmed anything.",
         "~700 became 42\nCandidates, not confirmed", AI),
        ("card", "", "Good science means doubting your own map.", "Doubt your own map", ""),
    ],
    8: [
        ("still", "p_blue_marble_wide.jpg", "There are three ways over the top of the world.",
         "Three ways over the\ntop of the world", "NASA Blue Marble via NASA GIBS"),
        ("still", "arctic_intersection.jpg", "The Northwest Passage, through Canada's Arctic islands.",
         "Northwest Passage", "USGS"),
        ("clip", "clip3.mp4", "The Northern Sea Route, along Russia's coast.",
         "Northern Sea Route", AI),
        ("clip", "clip0.mp4", "And the Transpolar Route, straight across the pole, which is still mostly theory. Each one trades distance for ice risk.",
         "Transpolar Route:\nstill mostly theory", AI),
        ("shot", "route_c.png", "My planner lets you compare Arctic and global routes in your browser.",
         "Compare routes free", ""),
        ("card", "", "Free, at arctic passage atlas dot com.", "Try it free", ""),
    ],
    9: [
        ("clip", "clip8.mp4", "Optical satellites need sunlight. But in the Arctic, the sun disappears for weeks.",
         "Optical satellites\nneed sunlight", AI),
        ("still", "p_modis_winter.jpg", "Cambridge Bay sees the sun for twenty four hours in midsummer, and none at all in deep winter.",
         "Deep winter:\nno optical image", "NASA MODIS via NASA GIBS"),
        ("still", "gibs_modis_2024-07-22.jpg", "That is why my Landsat analysis only uses July and August images, when the ground is clear and the light is good.",
         "July and August only:\nclear ground, good light", "NASA MODIS via NASA GIBS"),
        ("card", "", "Geomatics is partly knowing when not to trust the data.", "Know when not to\ntrust the data", ""),
    ],
    10: [
        ("clip", "clip9.mp4", "Every dot on a ship map is a radio message. Ships broadcast their position, and receivers pick it up.",
         "Every dot is\na radio message", AI),
        ("still", "p_blue_marble_wide.jpg", "In the Arctic, there are very few receivers.",
         "Very few receivers\nin the Arctic", "NASA Blue Marble via NASA GIBS"),
        ("clip", "clip5.mp4", "So a gap on the map can mean a ship went out of range, nothing more. I never call a gap suspicious.",
         "A gap is not suspicious", AI),
        ("still", "icebreakers_2.jpg", "And the shipping heat map drops ship names and ID numbers, so it shows traffic, not people.",
         "No names. No ID numbers.", "U.S. Coast Guard"),
        ("card", "", "Honest maps show their blind spots.", "Honest maps show\ntheir blind spots", ""),
    ],
}


def run(*args: str) -> None:
    result = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr[-1500:])


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out.strip())


def textfile(name: str, text: str) -> str:
    path = TMP / f"{name}.txt"
    path.write_text(text, encoding="utf-8", newline="\n")
    return str(path).replace("\\", "/").replace(":", "\\:")


def overlay_filters(tag: str, caption: str, credit: str, low: bool = False) -> str:
    size = 66
    top = 0.80 if low else 0.66
    filters = []
    if caption:
        filters.append(
            f"drawtext=fontfile='{FONT_BOLD}':textfile='{textfile(tag + 'c', caption)}':fontsize={size}:fontcolor=white:"
            f"line_spacing=14:x=(w-text_w)/2:y=h*{top}:box=1:boxcolor=0x06121c@0.55:boxborderw=26:"
            f"alpha='min(1,t/0.35)'"
        )
    if credit:
        filters.append(
            f"drawtext=fontfile='{FONT}':textfile='{textfile(tag + 'k', credit)}':fontsize=30:fontcolor=0xdfeaf1:"
            f"x=(w-text_w)/2:y=h-250:box=1:boxcolor=0x000000@0.35:boxborderw=10"
        )
    return ",".join(filters)


def render_segment(tag: str, kind: str, src: str, caption: str, credit: str, length: float) -> Path:
    out = TMP / f"{tag}.mp4"
    frames = max(2, round(length * FPS))
    fit = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
    overlay = overlay_filters(tag, caption, credit, low=(kind == "shot"))
    suffix = ("," + overlay) if overlay else ""
    final = ",fade=t=in:st=0:d=0.12,format=yuv420p"
    if kind == "clip":
        path = RAW / src
        # Stretch up to 1.35x slower to fill the segment, then hold the last frame.
        factor = max(1.0, min(1.35, length / duration(path)))
        vf = f"setpts={factor}*PTS,{fit},fps={FPS},tpad=stop_mode=clone:stop_duration=3{suffix}{final}"
        run("-i", str(path), "-vf", vf, "-t", f"{length:.3f}", "-an", "-r", str(FPS), str(out))
    elif kind == "video":
        path = ASSETS / src
        vf = f"{fit},fps={FPS},tpad=stop_mode=clone:stop_duration=3{suffix}{final}"
        run("-i", str(path), "-vf", vf, "-t", f"{length:.3f}", "-an", "-r", str(FPS), str(out))
    elif kind in ("still", "shot"):
        path = (ASSETS if kind == "still" else SHOTS) / src
        # Slow push-in (zoompan on a 2x supersampled frame avoids jitter).
        zoom = f"zoompan=z='1+0.0009*on':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS}"
        vf = f"scale=-2:{H * 2},crop={W * 2}:{H * 2},{zoom}{suffix}{final}"
        run("-loop", "1", "-i", str(path), "-vf", vf, "-t", f"{length:.3f}", "-an", "-r", str(FPS), str(out))
    else:  # card
        lines = [
            "drawbox=x=0:y=0:w=iw:h=ih:color=0x071521:t=fill",
            f"drawtext=fontfile='{FONT_BOLD}':text='Arctic Passage Atlas':fontsize=78:fontcolor=white:x=(w-text_w)/2:y=h*0.30",
            f"drawtext=fontfile='{FONT_BOLD}':textfile='{textfile(tag + 'c', caption)}':fontsize=72:fontcolor=0x7bdff2:"
            f"line_spacing=16:x=(w-text_w)/2:y=h*0.42",
            f"drawtext=fontfile='{FONT_BOLD}':text='{URL}':fontsize=64:fontcolor=0xffb454:x=(w-text_w)/2:y=h*0.62",
            f"drawtext=fontfile='{FONT}':text='Open-source Arctic data by Maheep Chowdhary':fontsize=36:fontcolor=0xcfe3f0:"
            f"x=(w-text_w)/2:y=h*0.70",
            f"drawtext=fontfile='{FONT}':text='Not for navigation. Not a surveillance system.':fontsize=32:fontcolor=0x9fb7c6:"
            f"x=(w-text_w)/2:y=h*0.75",
            "fade=t=in:st=0:d=0.2,format=yuv420p",
        ]
        run("-f", "lavfi", "-i", f"color=c=0x071521:s={W}x{H}:r={FPS}", "-vf", ",".join(lines), "-t", f"{length:.3f}", "-an", str(out))
    return out


def build(number: int) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    TMP.mkdir(parents=True, exist_ok=True)
    spec = REELS[number]
    voice_raw = RAW / f"voice{number}.wav"
    # Speed the narration up just enough to fit 29.2 s, never slowing it down.
    speed = max(1.0, duration(voice_raw) / 29.2)
    voice = TMP / f"voice{number}_fit.wav"
    run("-i", str(voice_raw), "-filter:a", f"atempo={speed:.4f}", str(voice))
    speech = duration(voice)

    words = [max(1, len(item[2].split())) for item in spec]
    cards_extra = 1.0  # the end card holds a second past the last word
    spoken_total = TOTAL - cards_extra
    lengths = [spoken_total * w / sum(words) for w in words]
    lengths[-1] += cards_extra

    parts: list[Path] = []
    for index, ((kind, src, _text, caption, credit), length) in enumerate(zip(spec, lengths), start=1):
        parts.append(render_segment(f"r{number}s{index}", kind, src, caption, credit, length))
    listing = TMP / f"r{number}.txt"
    listing.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8", newline="\n")
    silent = TMP / f"r{number}_silent.mp4"
    run("-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(silent))

    music = ASSETS / "backdrop_music.mp3"
    out = OUT / f"arctic-passage-atlas-reel-{number}.mp4"
    audio = (
        f"[1:a]loudnorm=I=-16:TP=-1.5:LRA=11,asplit=2[v1][v2];"
        f"[2:a]volume=0.5,atrim=0:{TOTAL},afade=t=out:st={TOTAL - 2}:d=2[m];"
        f"[m][v2]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[md];"
        f"[v1][md]amix=inputs=2:duration=first:normalize=0,apad,atrim=0:{TOTAL}[a]"
    )
    run("-i", str(silent), "-i", str(voice), "-stream_loop", "-1", "-i", str(music), "-filter_complex", audio,
        "-map", "0:v", "-map", "[a]", "-t", str(TOTAL), "-c:v", "libx264", "-preset", "medium", "-crf", "19",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out))
    print(f"reel {number}: {out.name} {duration(out):.1f}s (speech {speech:.1f}s)")
    return out


if __name__ == "__main__":
    wanted = [int(a) for a in sys.argv[1:]] or sorted(REELS)
    for n in wanted:
        build(n)
