"""Render the course banner as an explicit orthogonal workflow diagram."""

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch


BG = "#101827"
EDGE = "#7AA7B5"
MUTED = "#B7D1D5"
ROOT = Path(__file__).with_suffix(".png")


def box(ax, center, size, label, fill, stroke, text_color, fontsize=16):
    x, y = center
    width, height = size
    patch = FancyBboxPatch(
        (x - width / 2, y - height / 2),
        width,
        height,
        boxstyle="round,pad=0.004,rounding_size=0.020",
        linewidth=2.5,
        facecolor=fill,
        edgecolor=stroke,
        zorder=3,
    )
    ax.add_patch(patch)
    ax.text(
        x,
        y,
        label,
        ha="center",
        va="center",
        color=text_color,
        fontsize=fontsize,
        fontweight="bold",
        linespacing=1.05,
        zorder=4,
    )


def arrow(ax, points, label=None, label_xy=None, color=EDGE):
    for start, end in zip(points, points[1:]):
        x1, y1 = start
        x2, y2 = end
        if x1 != x2 and y1 != y2:
            raise ValueError(f"diagonal segment: {start} -> {end}")
        if x1 == x2:
            ax.vlines(x1, y1, y2, color=color, linewidth=2.2, zorder=1)
        else:
            ax.hlines(y1, x1, x2, color=color, linewidth=2.2, zorder=1)
    ax.annotate(
        "",
        xy=points[-1],
        xytext=points[-2],
        arrowprops={
            "arrowstyle": "-|>",
            "color": color,
            "linewidth": 1.4,
            "mutation_scale": 17,
        },
        zorder=2,
    )
    if label and label_xy:
        ax.text(
            *label_xy,
            label,
            ha="center",
            va="center",
            color=color,
            fontsize=12,
            zorder=4,
            bbox={"facecolor": BG, "edgecolor": "none", "pad": 1.5},
        )


fig, ax = plt.subplots(figsize=(16, 6), dpi=160, facecolor=BG)
ax.set_facecolor(BG)
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.axis("off")

ax.text(
    0.035,
    0.92,
    "SPECIALIZED AGENT WORKFLOW",
    color=MUTED,
    fontsize=25,
    fontweight="normal",
    ha="left",
    va="center",
)

# Main left-to-right spine.
box(ax, (0.075, 0.48), (0.09, 0.12), "INTAKE", "#E9F0F2", "#E9F0F2", "#172634", 13)
box(ax, (0.19, 0.48), (0.09, 0.12), "PLAN", "#C6DCE0", "#C6DCE0", "#172634", 13)
box(ax, (0.60, 0.48), (0.13, 0.13), "RECONCILE", "#BFD5D4", "#BFD5D4", "#172634", 13)
box(ax, (0.735, 0.48), (0.09, 0.13), "DRAFT", "#F0A45B", "#F0A45B", "#2A2116", 13)
box(ax, (0.87, 0.48), (0.11, 0.15), "HUMAN\nREVIEW", "#E6B86A", "#F7D28D", "#2A2116", 13)
box(ax, (0.87, 0.74), (0.11, 0.14), "VERIFY\n+ EXPORT", "#B8D8BE", "#78B584", "#17301D", 13)

arrow(ax, [(0.12, 0.48), (0.145, 0.48)])

# Parallel evidence occupies one compact stage between planning and synthesis.
cluster = FancyBboxPatch(
    (0.29, 0.18),
    0.23,
    0.60,
    boxstyle="round,pad=0.012,rounding_size=0.025",
    linewidth=1.8,
    linestyle=(0, (5, 5)),
    facecolor="none",
    edgecolor="#365B69",
    zorder=0,
)
ax.add_patch(cluster)
ax.text(
    0.305,
    0.75,
    "PARALLEL EVIDENCE",
    color=MUTED,
    fontsize=13,
    fontweight="bold",
    ha="left",
    va="center",
)

box(ax, (0.395, 0.65), (0.15, 0.11), "SOURCE CATALOG", "#294652", "#75AAB5", "#F7F3EA", 11)
box(ax, (0.395, 0.48), (0.15, 0.11), "RETRIEVE PASSAGES", "#294652", "#75AAB5", "#F7F3EA", 11)
box(ax, (0.395, 0.31), (0.15, 0.11), "EXTRACT CLAIMS", "#294652", "#75AAB5", "#F7F3EA", 11)

# Fan-out bus.
arrow(ax, [(0.235, 0.48), (0.27, 0.48), (0.27, 0.65), (0.32, 0.65)])
arrow(ax, [(0.235, 0.48), (0.32, 0.48)])
arrow(ax, [(0.235, 0.48), (0.27, 0.48), (0.27, 0.31), (0.32, 0.31)])
ax.text(0.27, 0.71, "fan-out", color=EDGE, fontsize=11, ha="center", va="center")

# Fan-in bus.
arrow(ax, [(0.47, 0.65), (0.515, 0.65), (0.515, 0.48), (0.535, 0.48)])
arrow(ax, [(0.47, 0.48), (0.535, 0.48)])
arrow(ax, [(0.47, 0.31), (0.515, 0.31), (0.515, 0.48), (0.535, 0.48)])
ax.text(0.515, 0.71, "fan-in", color=EDGE, fontsize=11, ha="center", va="center")

# Synthesis, review, approval, and bounded feedback.
arrow(ax, [(0.665, 0.48), (0.69, 0.48)])
arrow(ax, [(0.78, 0.48), (0.815, 0.48)])
arrow(ax, [(0.87, 0.555), (0.87, 0.67)], "approve", (0.91, 0.61), "#E6B86A")
arrow(
    ax,
    [(0.815, 0.43), (0.80, 0.43), (0.80, 0.31), (0.69, 0.31), (0.69, 0.415)],
    "edit / reject",
    (0.755, 0.27),
    "#E6B86A",
)
arrow(
    ax,
    [(0.60, 0.415), (0.60, 0.11), (0.19, 0.11), (0.19, 0.415)],
    "evidence gap",
    (0.42, 0.075),
    "#A6C7CD",
)

fig.savefig(ROOT, facecolor=BG, bbox_inches="tight", pad_inches=0.12)
plt.close(fig)
