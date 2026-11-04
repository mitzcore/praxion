#!/usr/bin/env python3
"""Assemble the Praxion demo film: 1920x1080 30 fps H.264 + AAC, <= 3:00.

Video: an ordered list of (source, in_s, dur_s); 0.4 s cross-dissolves between them (ffmpeg xfade).
Audio: music bed (ducked, faded) + narration lines placed at absolute times.
Usage: python3 assemble.py [--out final.mp4] [--no-xfade]
"""
import argparse, json, os, subprocess, sys
from pathlib import Path

F = Path(__file__).resolve().parent
OUT = F / "out"          # rendered scenes
CUTS = F / "cuts"
BROLL = F / "broll"
AUDIO = F / "audio"
FPS = 30
XF = 0.4                 # cross-dissolve seconds

def dur(p):
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                          "-of", "csv=p=0", str(p)]).decode().strip())

def run(cmd):
    print(" ".join(str(c) for c in cmd)[:400], file=sys.stderr)
    subprocess.run([str(c) for c in cmd], check=True)

def blend_scene_over_broll(scene, broll, out, dim=0.26, pad_s=0.0):
    """Scene (light text on near-black) composited over a dimmed B-roll clip with a 'lighten' blend.
    The B-roll is stretched to the scene length; pad_s freezes the scene's last frame that long."""
    d = dur(scene) + pad_s
    bd = dur(broll)
    setpts = f"setpts={d / bd:.5f}*PTS"
    pad = f",tpad=stop_mode=clone:stop_duration={pad_s:.3f}" if pad_s > 0 else ""
    run(["ffmpeg", "-v", "error", "-y", "-i", scene, "-i", broll, "-filter_complex",
         f"[1:v]{setpts},fps={FPS},scale=1920:1080,eq=saturation=0.7,"
         f"colorlevels=romax={dim}:gomax={dim}:bomax={dim},trim=0:{d},setpts=PTS-STARTPTS[bg];"
         f"[0:v]fps={FPS}{pad},format=gbrp[fg];[bg]format=gbrp[bg2];[bg2][fg]blend=all_mode=lighten,format=yuv420p[v]",
         "-map", "[v]", "-t", f"{d:.3f}", "-an", "-c:v", "libx264", "-crf", "17", "-preset", "medium", out])
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(F / "praxion_demo.mp4"))
    ap.add_argument("--no-xfade", action="store_true")
    args = ap.parse_args()
    work = F / "work"; work.mkdir(exist_ok=True)

    # --- pre-composites
    quote_bg = blend_scene_over_broll(OUT / "01_quote.mp4", BROLL / "plant.mp4", work / "01_quote_bg.mp4")
    close_bg = blend_scene_over_broll(OUT / "06_close.mp4", BROLL / "dc.mp4", work / "06_close_bg.mp4", pad_s=8.0)

    # --- EDL: (file, in, dur). Durations of scenes are whatever was rendered.
    def scene(name):
        p = OUT / f"{name}.mp4"; return (p, 0.0, dur(p))
    edl = [
        (quote_bg, 0.0, dur(quote_bg)),            # 1  quote over plant B-roll
        (CUTS / "fan_tap_zoom.mp4", 2.0, 5.0),     # 2  hand switches the fan on (22:17)
        (CUTS / "terminal.mp4", 0.0, 3.5),         # 3  temperature falling on the Mac
        scene("01_title"),                          # 4
        scene("02_problem"),                        # 5
        scene("03_loop"),                           # 6
        (CUTS / "tank_replay.mp4", 0.0, 8.0),      # 7  dashboard replay, simulated tank
        scene("03_simstat"),                        # 8
        scene("04_hwintro"),                        # 9
        (CUTS / "photo_4807.mp4", 0.0, 5.0),       # 10 the rig
        (CUTS / "fan_tap_wide.mp4", 1.5, 6.0),     # 11 fan on, wide
        (CUTS / "approach.mp4", 2.0, 6.0),         # 12 handheld approach to the board
        (CUTS / "board_close.mp4", 0.0, 6.0),      # 13 board close, heater LED
        (CUTS / "still_hw2_ab.mp4", 0.0, 5.0),     # 14 board A/B panel
        scene("04_hwnumbers"),                      # 15
        scene("05_results"),                        # 16
        (CUTS / "stills_strips.mp4", 0.0, 4.0),    # 17 four board pairs
        (close_bg, 0.0, dur(close_bg)),            # 18 close over data-centre B-roll
    ]
    # clamp every segment to what its file really holds (xfade breaks silently past an input's end)
    fixed = []
    for src, ins, d in edl:
        real = dur(src) - ins
        if real + 0.01 < d:
            print(f"WARNING {Path(src).name}: wanted {d:.2f}s from {ins:.2f}s, file holds {real:.2f}s -> clamped", file=sys.stderr)
            d = round(real - 0.02, 2)
        fixed.append((src, ins, d))
    edl = fixed
    # narration: (file, start_s) — starts are computed from segment starts below
    narr_at = {"n1": 1, "n2": 4, "n3": 5, "n4s": 6, "n5": 8, "n6s": 9, "n7": 15, "n8s": 16, "n9": 18}
    narr_offset = {"n1": 0.8, "n2": 0.4, "n3": 1.7, "n4s": 0.4, "n5": 0.3, "n6s": 0.5, "n7": 0.4, "n8s": 0.6, "n9": 0.4}

    # segment start times on the final timeline (xfade overlaps XF)
    xf = 0.0 if args.no_xfade else XF
    starts, t = [], 0.0
    for i, (_, _, d) in enumerate(edl):
        starts.append(t)
        t += d - (xf if i < len(edl) - 1 else 0.0)
    total = t
    print(json.dumps({"segments": [{"i": i + 1, "start": round(starts[i], 2), "dur": round(edl[i][2], 2), "src": Path(edl[i][0]).name} for i in range(len(edl))], "total_s": round(total, 2)}, indent=1))

    # --- video graph
    inputs, filters, labels = [], [], []
    for i, (src, ins, d) in enumerate(edl):
        inputs += ["-ss", f"{ins:.3f}", "-t", f"{d:.3f}", "-i", str(src)]
        filters.append(f"[{i}:v]fps={FPS},scale=1920:1080:flags=lanczos,setsar=1,format=yuv420p,setpts=PTS-STARTPTS[v{i}]")
        labels.append(f"v{i}")
    if args.no_xfade:
        filters.append("".join(f"[{l}]" for l in labels) + f"concat=n={len(labels)}:v=1:a=0[vout]")
    else:
        prev = labels[0]; acc = edl[0][2]
        for i in range(1, len(labels)):
            out = f"x{i}"
            off = acc - XF
            filters.append(f"[{prev}][{labels[i]}]xfade=transition=fade:duration={XF}:offset={off:.3f}[{out}]")
            acc = off + edl[i][2]
            prev = out
        filters.append(f"[{prev}]copy[vout]")

    # --- audio graph: music + narration
    ai = len(edl)
    inputs += ["-i", str(AUDIO / "music.mp3")]
    music_in = ai; ai += 1
    narr_filters, narr_labels = [], []
    voice_dir = AUDIO / os.environ.get("VOICE_DIR", "arthur")
    tempo = {"n4s": 1.04, "n8s": 1.05}   # gentle time-stretch where a line would otherwise collide with the next
    prev_end, placed = -1.0, []
    for k, (name, seg) in enumerate(narr_at.items()):
        p = voice_dir / f"{name}.wav"
        d = dur(p) / tempo.get(name, 1.0)
        start = max(starts[seg - 1] + narr_offset[name], prev_end + 0.35)
        if start + d > total - 0.3:
            print(f"WARNING {name}: ends at {start + d:.1f}s, film ends {total:.1f}s", file=sys.stderr)
        placed.append((name, round(start, 2), round(start + d, 2)))
        prev_end = start + d
        inputs += ["-i", str(p)]
        at = f"atempo={tempo[name]}," if name in tempo else ""
        narr_filters.append(f"[{ai}:a]aformat=sample_rates=48000:channel_layouts=stereo,{at}volume=1.0,adelay={int(start * 1000)}|{int(start * 1000)}[n{k}]")
        narr_labels.append(f"n{k}"); ai += 1
    print("narration:", placed)
    filters += narr_filters
    filters.append("".join(f"[{l}]" for l in narr_labels) + f"amix=inputs={len(narr_labels)}:normalize=0:dropout_transition=0[narr]")
    filters.append(f"[{music_in}:a]aformat=sample_rates=48000:channel_layouts=stereo,atrim=0:{total:.3f},afade=t=in:st=0:d=1.5,afade=t=out:st={total - 4:.3f}:d=4,volume=0.16[mus]")
    filters.append("[narr][mus]amix=inputs=2:normalize=0:dropout_transition=0,alimiter=limit=0.95[aout]")

    cmd = ["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(filters),
           "-map", "[vout]", "-map", "[aout]", "-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "18",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", args.out]
    run(cmd)
    print("final:", args.out, round(dur(args.out), 2), "s")

if __name__ == "__main__":
    main()
