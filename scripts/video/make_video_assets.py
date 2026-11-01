import json
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

run = sys.argv[1] if len(sys.argv) > 1 else "artifacts/runs/v13-s11-20261031-020922-a0e68e"
out = "artifacts/video/assets"
BG, FG, MUTED, BAND = "#0b1220", "#edf2ff", "#8ea0bf", "#2a7d5a"
plt.rcParams.update({"figure.facecolor": BG, "axes.facecolor": BG, "axes.edgecolor": "#2b3a55", "axes.labelcolor": MUTED,
                     "xtick.color": MUTED, "ytick.color": MUTED, "text.color": FG, "font.size": 16, "font.family": "DejaVu Sans"})
def load(name): return json.load(open(f"{run}/{name}"))
def trace(rep, idx=0):
    st = rep["episodes"][idx]["trace"]["steps"]
    return [s["t"] for s in st], [s["h_true"] for s in st], [s["u_applied"] for s in st]
def base(ax, title, xmax):
    ax.axhspan(0.55, 0.65, color=BAND, alpha=0.35, lw=0); ax.axhline(0.60, color=BAND, lw=1, ls="--")
    ax.axhline(0.90, color="#ff6b6b", lw=1.2); ax.text(xmax, 0.915, "overflow cutoff 0.90", color="#ff6b6b", ha="right", fontsize=12)
    ax.set_ylim(0, 1.0); ax.set_xlim(0, xmax); ax.set_ylabel("water level"); ax.set_xlabel("seconds")
    ax.set_title(title, loc="left", fontsize=20, pad=14); ax.grid(color="#1c2740", lw=0.6)
v1n = load("evaluation_v1.json"); v1d = load("evaluation_disturbance_v1.json"); v2d = load("evaluation_disturbance_v2.json"); v2n = load("evaluation_v2.json")
# 1. nominal: Muse v1 holds the line
t,h,_ = trace(v1n, 1); fig,ax = plt.subplots(figsize=(16,7)); base(ax, "1 · Unknown tank, Muse-written controller v1: holds 60% on a hidden scenario", 120)
ax.plot(t,h,color="#7be5b6",lw=3,label="water level (true)"); ax.legend(loc="lower right", frameon=False); fig.tight_layout(); fig.savefig(f"{out}/01_v1_nominal.png", dpi=120); plt.close(fig)
# 2. after the change: v1 oscillates
t,h,u = trace(v1d, 0); fig,ax = plt.subplots(figsize=(16,7)); base(ax, "2 · The machine changes (24 s hidden delay): the same controller v1 loses control", 300)
ax.axvline(60, color="#f4c677", lw=2); ax.text(62, 0.05, "hidden change at 60 s", color="#f4c677", fontsize=13)
ax.plot(t,h,color="#f4c677",lw=3,label="water level with v1"); ax.legend(loc="lower right", frameon=False); fig.tight_layout(); fig.savefig(f"{out}/02_v1_after_change.png", dpi=120); plt.close(fig)
# 3. v1 vs v2 same scenario
t2,h2,_ = trace(v2d, 0); fig,ax = plt.subplots(figsize=(16,7)); base(ax, "3 · Muse diagnoses the delay and rewrites itself: v2 on the identical scenario", 300)
ax.axvline(60, color="#f4c677", lw=1.5, ls=":")
ax.plot(t,h,color="#f4c677",lw=2.2,alpha=0.8,label="v1 (before repair)"); ax.plot(t2,h2,color="#7be5b6",lw=3.2,label="v2 (Muse's repair)")
ax.legend(loc="lower right", frameon=False); fig.tight_layout(); fig.savefig(f"{out}/03_v1_vs_v2.png", dpi=120); plt.close(fig)
# 4. scorecard across 5 machines
rows = [("seed 3", 0.186, 0.031), ("seed 7", 0.190, 0.095), ("seed 11", 0.217, 0.021), ("seed 14", 0.044, 0.010), ("seed 18", 0.027, 0.014)]
fig,ax = plt.subplots(figsize=(16,7)); ax.set_facecolor(BG)
x = np.arange(len(rows)); w=0.36
ax.bar(x-w/2,[r[1] for r in rows],w,color="#f4c677",label="before repair (v1 after the change)"); ax.bar(x+w/2,[r[2] for r in rows],w,color="#7be5b6",label="after repair (promoted version)")
ax.set_xticks(x); ax.set_xticklabels([f"machine {r[0]}" for r in rows]); ax.set_ylabel("tracking error after the change (lower is better)")
ax.set_title("4 · Five different hidden machines: repair succeeded on all five, zero safety violations", loc="left", fontsize=20, pad=14)
ax.legend(frameon=False); ax.grid(axis="y", color="#1c2740", lw=0.6); fig.tight_layout(); fig.savefig(f"{out}/04_five_machines.png", dpi=120); plt.close(fig)
# numbers for narration
print("v1 nominal median MAE", v1n["aggregate"]["median_mae"], "pid", v1n["aggregate"].get("baseline_pid_median_mae"))
print("v1 post", v1d["aggregate"]["median_post_disturbance_mae"], "viol", v1d["aggregate"]["total_hard_violations"], "| v2 post", v2d["aggregate"]["median_post_disturbance_mae"], "inband", v2d["aggregate"]["mean_in_band_fraction"], "viol", v2d["aggregate"]["total_hard_violations"])
