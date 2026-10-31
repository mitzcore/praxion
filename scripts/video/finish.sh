#!/bin/bash
# Render the Higgsedit project, mix the narration at each beat's offset, mux, and (optionally) upload.
# Runs inside the Higgsfield sandbox (higgsedit + ffmpeg). UPLOAD_URL is a presigned PUT URL from media_upload.
set -e
cd "$(dirname "$0")"
higgsedit render . --out renders/master.mp4 --bitrate 10M --workers 6
python3 - <<'PY'
import json, subprocess
T = json.load(open("timing.json"))
total = T[-1]["start"] + T[-1]["dur"]
inputs, filters, labels = [], [], []
for i, t in enumerate(T, 1):
    inputs += ["-i", f"media/vo/vo{i}.mp3"]
    ms = int(t["vo_at"] * 1000)
    filters.append(f"[{i-1}:a]aresample=48000,adelay={ms}|{ms}[a{i}]")
    labels.append(f"[a{i}]")
filters.append(f"anullsrc=r=48000:cl=stereo:d={total:.2f}[base]")
filters.append("".join(labels) + f"[base]amix=inputs={len(T)+1}:normalize=0:duration=longest[mix]")
subprocess.check_call(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(filters), "-map", "[mix]",
                       "-t", f"{total:.2f}", "-c:a", "aac", "-b:a", "192k", "renders/vo.m4a"])
subprocess.check_call(["ffmpeg", "-y", "-i", "renders/master.mp4", "-i", "renders/vo.m4a", "-map", "0:v", "-map", "1:a",
                       "-c:v", "copy", "-c:a", "copy", "-shortest", "-movflags", "+faststart", "renders/praxion_demo.mp4"])
PY
if [ -n "$UPLOAD_URL" ]; then
  curl -s -o /dev/null -w "upload http %{http_code}\n" -X PUT -H "Content-Type: video/mp4" --data-binary @renders/praxion_demo.mp4 "$UPLOAD_URL"
fi
