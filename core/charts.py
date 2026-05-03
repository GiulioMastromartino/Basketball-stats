import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import matplotlib.ticker as mticker
from matplotlib.lines import Line2D
import numpy as np
from scipy.interpolate import make_interp_spline
import base64
from io import BytesIO
from core.models import ShotEvent, PlayerStat, Game, db
from core.utils import calculate_possessions, calculate_ortg, parse_minutes

MAX_SHOTS_PER_CHART = 5000

# ── Design tokens (mirror CSS variables in player_report_pdf.html) ──────────
BG         = "#0a0a0c"
BG_CARD    = "#141417"
BG_CELL    = "#1c1c1f"
BORDER     = "#2a2a30"
CYAN       = "#00f2ff"
GREEN      = "#00e676"
RED        = "#ff1744"
GOLD       = "#fbbf24"
DIM        = "#64748b"
WHITE      = "#e2e8f0"
COURT_LINE = "#3a3a44"

FONT_FAMILY = "monospace"


def _apply_dark_style(fig, axes):
    fig.patch.set_facecolor(BG)
    for ax in (axes if hasattr(axes, "__iter__") else [axes]):
        ax.set_facecolor(BG_CARD)
        ax.tick_params(colors=DIM, labelsize=7, length=3)
        ax.xaxis.label.set_color(DIM)
        ax.yaxis.label.set_color(DIM)
        for spine in ax.spines.values():
            spine.set_edgecolor(BORDER)
            spine.set_linewidth(0.8)


def _savefig_b64(fig, dpi=120):
    img_io = BytesIO()
    fig.savefig(img_io, format="png", dpi=dpi, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    img_io.seek(0)
    data = base64.b64encode(img_io.read()).decode()
    plt.close(fig)
    return data


def _smooth(x, y, resolution=300):
    """Return smoothed xs, ys via cubic B-spline. Falls back to raw if < 4 pts."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(x) < 4:
        return x, y
    k = min(3, len(x) - 1)
    spl = make_interp_spline(x, y, k=k)
    xs = np.linspace(x[0], x[-1], resolution)
    return xs, spl(xs)


# ── Shot charts ──────────────────────────────────────────────────────────────

def generate_shot_chart(player_name, game_ids, db_session=None):
    session = db_session or db.session
    query = session.query(ShotEvent).filter(ShotEvent.player_name == player_name)
    if game_ids is not None:
        query = query.filter(ShotEvent.game_id.in_(game_ids))
    shots = (
        query.filter(ShotEvent.x_loc.isnot(None))
             .filter(ShotEvent.y_loc.isnot(None))
             .limit(MAX_SHOTS_PER_CHART)
             .all()
    )
    if not shots:
        return ""
    return _create_court_plot(shots)


def generate_team_shot_chart(game_ids, db_session=None):
    session = db_session or db.session
    shots = (
        session.query(ShotEvent)
               .filter(ShotEvent.game_id.in_(game_ids))
               .filter(ShotEvent.x_loc.isnot(None))
               .filter(ShotEvent.y_loc.isnot(None))
               .limit(MAX_SHOTS_PER_CHART)
               .all()
    )
    if not shots:
        return ""
    return _create_court_plot(shots, is_team=True)


def _draw_court(ax, lw=1.5):
    kw = dict(color=COURT_LINE, linewidth=lw, zorder=1)
    for xs, ys in [([0,500],[0,0]), ([0,500],[470,470]),
                   ([0,0],[0,470]), ([500,500],[0,470])]:
        ax.plot(xs, ys, **kw)
    pw, ph = 163.3, 193.3
    px = (500 - pw) / 2
    ax.add_patch(patches.Rectangle((px, 0), pw, ph,
                                    lw=lw, edgecolor=COURT_LINE, facecolor="#1a1a20"))
    ax.add_patch(patches.Circle((250, 195.3), 60,
                                 lw=lw, edgecolor=COURT_LINE, facecolor="none"))
    ax.plot([30,30], [0, 99.7], **kw)
    ax.plot([470,470], [0, 99.7], **kw)
    ax.add_patch(patches.Arc((250, 99.7), 440, 440,
                              theta1=0, theta2=180,
                              lw=lw, edgecolor=COURT_LINE))
    ax.add_patch(patches.Arc((250, 52.5), 83.32, 83.32,
                              theta1=0, theta2=180,
                              lw=lw, edgecolor=COURT_LINE))
    ax.add_patch(patches.Circle((250, 52.5), 7.5,
                                 lw=lw, edgecolor=GOLD, facecolor="none", zorder=3))
    ax.plot([220, 280], [40, 40], color=GOLD, linewidth=lw, zorder=3)
    ax.add_patch(patches.Arc((250, 470), 120, 120,
                              theta1=180, theta2=360,
                              lw=lw, edgecolor=COURT_LINE))


def _create_court_plot(shots, is_team=False):
    try:
        fig, ax = plt.subplots(figsize=(7, 7.2))
        fig.patch.set_facecolor(BG)
        ax.set_facecolor(BG)
        _draw_court(ax)
        makes  = [s for s in shots if s.result == "made"]
        misses = [s for s in shots if s.result == "missed"]
        if makes:
            ax.scatter([s.x_loc for s in makes], [s.y_loc for s in makes],
                       c=GREEN, s=55, alpha=0.75, edgecolors="#005c2e",
                       linewidth=0.8, marker="o", label="Made", zorder=4)
        if misses:
            ax.scatter([s.x_loc for s in misses], [s.y_loc for s in misses],
                       c=RED, s=55, alpha=0.65, edgecolors="#7a0010",
                       linewidth=0.8, marker="x", label="Missed", zorder=4)
        total  = len(shots)
        n_made = len(makes)
        fg_pct = (n_made / total * 100) if total > 0 else 0
        if is_team:
            label = f"Team  {n_made}/{total}  ({fg_pct:.1f}%)"
        else:
            tp  = [s for s in shots if s.shot_type == "3pt"]
            tpm = [s for s in tp if s.result == "made"]
            t2  = [s for s in shots if s.shot_type != "3pt"]
            t2m = [s for s in t2 if s.result == "made"]
            tp_pct = (len(tpm)/len(tp)*100) if tp else 0
            t2_pct = (len(t2m)/len(t2)*100) if t2 else 0
            label = (f"FG {n_made}/{total} ({fg_pct:.1f}%)   "
                     f"2PT {len(t2m)}/{len(t2)} ({t2_pct:.1f}%)   "
                     f"3PT {len(tpm)}/{len(tp)} ({tp_pct:.1f}%)")
        ax.text(250, 492, label, ha="center", va="bottom", fontsize=8,
                fontfamily=FONT_FAMILY, color=WHITE,
                bbox=dict(boxstyle="round,pad=0.4", facecolor=BG_CARD,
                          edgecolor=BORDER, linewidth=0.8))
        legend = ax.legend(loc="upper left", fontsize=8, framealpha=0, labelcolor=WHITE)
        for t in legend.get_texts():
            t.set_fontfamily(FONT_FAMILY)
        ax.set_xlim(-15, 515)
        ax.set_ylim(-15, 510)
        ax.set_aspect("equal")
        ax.axis("off")
        plt.tight_layout(pad=0.3)
        return _savefig_b64(fig, dpi=130)
    except Exception:
        plt.close("all")
        return ""


# ── Player scoring + +/- trend  (smooth, full-width, single chart) ───────────

def generate_player_charts(stats, game_map, player_name, db_session=None):
    if not stats:
        return {"chart_scoring": ""}

    try:
        dates, points, pm_vals = [], [], []
        for s in stats:
            game = game_map.get(s.game_id)
            if game:
                dates.append(game.date)
                points.append(s.points)
                pm_vals.append(s.plus_minus if (game.source == "LIVE") else None)

        n = len(dates)
        if n == 0:
            return {"chart_scoring": ""}

        x = np.arange(n, dtype=float)

        # ── figure: tall single chart ──
        fig, ax1 = plt.subplots(figsize=(13, 5))
        _apply_dark_style(fig, [ax1])

        # ── smooth points curve + filled area ──
        xs, ys = _smooth(x, points)
        # clamp negatives introduced by spline at edges
        ys = np.clip(ys, 0, None)

        ax1.fill_between(xs, ys, alpha=0.18, color=CYAN, zorder=2)
        ax1.plot(xs, ys, color=CYAN, linewidth=2.2, zorder=3, label="Points (smooth)")
        # actual data dots
        ax1.scatter(x, points, color=CYAN, s=30, zorder=4, edgecolors=BG_CARD,
                    linewidth=0.8)
        # value labels above dots
        for xi, val in zip(x, points):
            ax1.text(xi, val + max(points) * 0.04, str(val),
                     ha="center", va="bottom", fontsize=6.5,
                     color=DIM, fontfamily=FONT_FAMILY)

        # ── 3-game MA (smooth) ──
        if n >= 3:
            ma = np.array([sum(points[max(0,i-2):i+1]) / min(3, i+1)
                           for i in range(n)], dtype=float)
            xs_ma, ys_ma = _smooth(x, ma)
            ax1.plot(xs_ma, ys_ma, color=GOLD, linewidth=1.6, linestyle="--",
                     zorder=3, alpha=0.85, label="3-G MA")

        y_max = max(points) if points else 1
        ax1.set_ylim(0, y_max * 1.35)
        ax1.set_ylabel("Points", color=DIM, fontsize=8, fontfamily=FONT_FAMILY)
        ax1.tick_params(axis="y", labelcolor=DIM, labelsize=7)
        ax1.yaxis.set_major_locator(mticker.MaxNLocator(integer=True, nbins=6))
        ax1.grid(True, axis="y", color=BORDER, linewidth=0.5, alpha=0.6, zorder=0)

        # ── secondary axis: +/- smooth ──
        ax2 = ax1.twinx()
        ax2.set_facecolor(BG_CARD)
        for spine in ax2.spines.values():
            spine.set_edgecolor(BORDER)

        live_x  = np.array([i for i, pm in enumerate(pm_vals) if pm is not None],
                            dtype=float)
        live_pm = np.array([pm for pm in pm_vals if pm is not None], dtype=float)

        if len(live_pm) >= 2:
            xs_pm, ys_pm = _smooth(live_x, live_pm)
            # split into positive / negative segments
            pos_mask = ys_pm >= 0
            neg_mask = ~pos_mask
            # plot as two layers with fill
            ax2.fill_between(xs_pm, ys_pm, 0,
                             where=pos_mask, color=GREEN, alpha=0.15, zorder=1)
            ax2.fill_between(xs_pm, ys_pm, 0,
                             where=neg_mask, color=RED, alpha=0.15, zorder=1)
            # single coloured line
            ax2.plot(xs_pm, ys_pm, color=WHITE, linewidth=1.4, alpha=0.6, zorder=2)
            # original dots coloured
            ax2.scatter(live_x, live_pm,
                        c=[GREEN if v >= 0 else RED for v in live_pm],
                        s=24, zorder=3, edgecolors="none")
            ax2.axhline(0, color=BORDER, linewidth=0.8, zorder=1)
            pm_abs = float(np.max(np.abs(live_pm))) if len(live_pm) else 1
            ax2.set_ylim(-pm_abs * 1.8, pm_abs * 1.8)
            ax2.set_ylabel("+/-", color=DIM, fontsize=8, fontfamily=FONT_FAMILY)
            ax2.tick_params(axis="y", labelcolor=DIM, labelsize=7)
        elif len(live_pm) == 1:
            ax2.scatter(live_x, live_pm,
                        c=[GREEN if live_pm[0] >= 0 else RED],
                        s=24, zorder=3, edgecolors="none")

        # ── x-axis labels ──
        step = max(1, n // 20)   # never crowd more than ~20 labels
        shown = list(range(0, n, step))
        ax1.set_xticks(shown)
        ax1.set_xticklabels(
            [str(dates[i])[-5:] for i in shown],
            rotation=40, ha="right", fontsize=6.5,
            fontfamily=FONT_FAMILY, color=DIM
        )
        ax1.set_xlim(-0.5, n - 0.5)

        # ── legend ──
        handles = [
            Line2D([0],[0], color=CYAN, linewidth=2.2, label="Points"),
            Line2D([0],[0], color=GOLD, linewidth=1.6, linestyle="--", label="3-G MA"),
        ]
        if len(live_pm) >= 1:
            handles += [
                Line2D([0],[0], color=GREEN, linewidth=2, label="+/- pos"),
                Line2D([0],[0], color=RED,   linewidth=2, label="+/- neg"),
            ]
        leg = ax1.legend(handles=handles, loc="upper left", fontsize=7.5,
                         framealpha=0.0, labelcolor=WHITE)
        for t in leg.get_texts():
            t.set_fontfamily(FONT_FAMILY)

        fig.suptitle(f"{player_name}  —  Scoring & +/- Trend",
                     color=WHITE, fontsize=10, fontfamily=FONT_FAMILY,
                     x=0.5, y=1.02)

        plt.tight_layout(pad=0.6)
        return {"chart_scoring": _savefig_b64(fig, dpi=140)}

    except Exception:
        plt.close("all")
        return {"chart_scoring": ""}


# ── Team scoring trend ───────────────────────────────────────────────────────

def generate_team_scoring_trend(games):
    if not games:
        return ""
    try:
        n = len(games)
        x = np.arange(n, dtype=float)
        team_scores = np.array([g.team_score for g in games], dtype=float)
        opp_scores  = np.array([g.opponent_score for g in games], dtype=float)

        fig, ax = plt.subplots(figsize=(10, 4))
        _apply_dark_style(fig, [ax])

        xs, ys_t = _smooth(x, team_scores)
        _,  ys_o = _smooth(x, opp_scores)
        ys_t = np.clip(ys_t, 0, None)
        ys_o = np.clip(ys_o, 0, None)

        ax.fill_between(xs, ys_t, ys_o,
                        where=(ys_t >= ys_o), color=GREEN, alpha=0.12, zorder=1)
        ax.fill_between(xs, ys_t, ys_o,
                        where=(ys_t <  ys_o), color=RED,   alpha=0.12, zorder=1)

        ax.plot(xs, ys_t, color=GREEN, linewidth=2, label="Team", zorder=3)
        ax.plot(xs, ys_o, color=RED,   linewidth=2, linestyle="--",
                label="Opponent", zorder=3)
        ax.scatter(x, team_scores, color=GREEN, s=22, zorder=4, edgecolors="none")
        ax.scatter(x, opp_scores,  color=RED,   s=22, zorder=4,
                   edgecolors="none", marker="s")

        avg_t = float(team_scores.mean())
        avg_o = float(opp_scores.mean())
        ax.axhline(avg_t, color=GREEN, linewidth=0.8, linestyle=":",
                   alpha=0.6, label=f"Avg {avg_t:.1f}")
        ax.axhline(avg_o, color=RED,   linewidth=0.8, linestyle=":",
                   alpha=0.6, label=f"Avg {avg_o:.1f}")

        step = max(1, n // 10)
        ax.set_xticks(x[::step])
        ax.set_xticklabels([str(int(i)+1) for i in x[::step]],
                           fontsize=7, fontfamily=FONT_FAMILY, color=DIM)
        ax.set_xlabel("Game", color=DIM, fontsize=8, fontfamily=FONT_FAMILY)
        ax.set_ylabel("Points", color=DIM, fontsize=8, fontfamily=FONT_FAMILY)
        ax.grid(True, color=BORDER, linewidth=0.5, alpha=0.7, zorder=0)
        ax.set_xlim(-0.5, n - 0.5)

        leg = ax.legend(fontsize=7, framealpha=0, labelcolor=WHITE, loc="best")
        for t in leg.get_texts():
            t.set_fontfamily(FONT_FAMILY)

        fig.suptitle("Team Scoring Trends", color=WHITE,
                     fontsize=9, fontfamily=FONT_FAMILY)
        plt.tight_layout(pad=0.5)
        return _savefig_b64(fig, dpi=120)
    except Exception:
        plt.close("all")
        return ""


# ── Quarter scoring chart ────────────────────────────────────────────────────

def generate_quarter_scoring_base64(chart_data, title):
    try:
        labels = chart_data.get("labels", [])
        points = chart_data.get("points", [])
        fg_pct = chart_data.get("fg_pct", [])
        tp_pct = chart_data.get("tp_pct", [])
        if not labels or not points:
            return ""

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7, 5), sharex=True)
        _apply_dark_style(fig, [ax1, ax2])

        q_colors = [CYAN, GOLD, GREEN, RED]
        bar_c = [q_colors[i % 4] for i in range(len(labels))]
        bars = ax1.bar(labels, points, color=bar_c, alpha=0.8,
                       edgecolor=BG, linewidth=1.2, zorder=2)
        ax1.set_ylabel("PPG", color=DIM, fontsize=8, fontfamily=FONT_FAMILY)
        ax1.yaxis.set_major_locator(mticker.MaxNLocator(integer=True, nbins=4))
        ax1.grid(True, axis="y", color=BORDER, linewidth=0.5, alpha=0.7, zorder=0)
        for bar, val in zip(bars, points):
            ax1.text(bar.get_x() + bar.get_width()/2,
                     bar.get_height() + max(points)*0.02,
                     f"{val:.1f}", ha="center", va="bottom",
                     fontsize=8, color=WHITE, fontfamily=FONT_FAMILY)
        ax1.set_title(title, color=WHITE, fontsize=9, fontfamily=FONT_FAMILY, pad=6)

        xr = np.arange(len(labels), dtype=float)
        if fg_pct:
            xs_fg, ys_fg = _smooth(xr, np.array(fg_pct, dtype=float))
            ax2.plot(xs_fg, np.clip(ys_fg, 0, 100), color=GREEN, linewidth=2,
                     label="FG%", zorder=3)
            ax2.scatter(xr, fg_pct, color=GREEN, s=22, zorder=4, edgecolors="none")
        if tp_pct:
            xs_tp, ys_tp = _smooth(xr, np.array(tp_pct, dtype=float))
            ax2.plot(xs_tp, np.clip(ys_tp, 0, 100), color=RED, linewidth=2,
                     linestyle="--", label="3PT%", zorder=3)
            ax2.scatter(xr, tp_pct, color=RED, s=22, zorder=4, edgecolors="none")
        ax2.set_ylim(0, 105)
        ax2.set_ylabel("%", color=DIM, fontsize=8, fontfamily=FONT_FAMILY)
        ax2.set_xlabel("Quarter", color=DIM, fontsize=8, fontfamily=FONT_FAMILY)
        ax2.set_xticks(range(len(labels)))
        ax2.set_xticklabels(labels, fontsize=8, fontfamily=FONT_FAMILY, color=DIM)
        ax2.grid(True, color=BORDER, linewidth=0.5, alpha=0.7, zorder=0)
        if fg_pct or tp_pct:
            leg = ax2.legend(fontsize=7, framealpha=0, labelcolor=WHITE)
            for t in leg.get_texts():
                t.set_fontfamily(FONT_FAMILY)
        plt.tight_layout(pad=0.5)
        return _savefig_b64(fig, dpi=120)
    except Exception:
        plt.close("all")
        return ""


# ── Shooting trend line chart ────────────────────────────────────────────────

def generate_shooting_trend_base64(chart_data, title):
    try:
        labels = chart_data.get("labels", [])
        fg_pct = chart_data.get("fg_pct", [])
        tp_pct = chart_data.get("tp_pct", [])
        if not labels:
            return ""

        fig, ax = plt.subplots(figsize=(8, 3))
        _apply_dark_style(fig, [ax])

        xr = np.arange(len(labels), dtype=float)
        if fg_pct:
            xs, ys = _smooth(xr, np.array(fg_pct, dtype=float))
            ax.fill_between(xs, np.clip(ys, 0, 100), alpha=0.12, color=GREEN)
            ax.plot(xs, np.clip(ys, 0, 100), color=GREEN, linewidth=2,
                    label="FG%", zorder=3)
            ax.scatter(xr, fg_pct, color=GREEN, s=20, zorder=4, edgecolors="none")
        if tp_pct:
            xs, ys = _smooth(xr, np.array(tp_pct, dtype=float))
            ax.plot(xs, np.clip(ys, 0, 100), color=RED, linewidth=2,
                    linestyle="--", label="3PT%", zorder=3)
            ax.scatter(xr, tp_pct, color=RED, s=20, zorder=4, edgecolors="none")

        ax.set_ylim(0, 100)
        ax.set_ylabel("%", color=DIM, fontsize=8, fontfamily=FONT_FAMILY)
        ax.set_title(title, color=WHITE, fontsize=9, fontfamily=FONT_FAMILY, pad=6)
        ax.grid(True, color=BORDER, linewidth=0.5, alpha=0.7, zorder=0)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, rotation=35, ha="right",
                           fontsize=7, fontfamily=FONT_FAMILY, color=DIM)
        plt.yticks(fontsize=7, color=DIM)
        if fg_pct or tp_pct:
            leg = ax.legend(fontsize=7, framealpha=0, labelcolor=WHITE)
            for t in leg.get_texts():
                t.set_fontfamily(FONT_FAMILY)
        plt.tight_layout(pad=0.5)
        return _savefig_b64(fig, dpi=120)
    except Exception:
        plt.close("all")
        return ""
