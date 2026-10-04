"""Figures for the paper and appendix.  Every figure is drawn at its printed size with
>= 10 pt text so no label shrinks below the brief's minimum."""
import json, sys, math
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch
sys.path.insert(0, str(Path(__file__).parent))
from geom import *
from scenarios import run, equity, futures, metrics
from protocol import account_state, World

R = Path(__file__).resolve().parents[1] / 'results'
F = Path(__file__).resolve().parents[1] / 'paper' / 'figs'
F.mkdir(parents=True, exist_ok=True)
plt.rcParams.update({'font.size': 10, 'axes.titlesize': 10, 'axes.labelsize': 10, 'xtick.labelsize': 10,
                     'ytick.labelsize': 10, 'legend.fontsize': 10, 'font.family': 'DejaVu Sans',
                     'svg.fonttype': 'none', 'pdf.fonttype': 42, 'axes.spines.top': False, 'axes.spines.right': False})
C = dict(earth='#2f6db5', mars='#c4472d', ceres='#6a8f3a', relay='#7a6aa8', direct='#d08a1e', ink='#222222',
         grey='#888888', alice='#2f6db5', cara='#6a8f3a', escrow='#c4472d', transit='#d08a1e')
H = HOUR


def save(fig, name):
    fig.savefig(F / f'{name}.svg', bbox_inches='tight', pad_inches=0.02)
    fig.savefig(F / f'{name}.pdf', bbox_inches='tight', pad_inches=0.02)
    fig.savefig(F / f'{name}.png', dpi=220, bbox_inches='tight', pad_inches=0.02)
    plt.close(fig)


# ---------------------------------------------------------------- Figure: S1a swimlane
def fig_swimlane():
    w, tr = run([(equity, dict(tag='EQ'))], until_h=6)
    lanes = ['Alice (Earth)', 'Earth exchange', 'Relay A', 'Mars exchange', 'Bob (Mars)']
    y = {n: len(lanes) - 1 - i for i, n in enumerate(lanes)}
    node_lane = {'Earth': 'Earth exchange', 'Relay A': 'Relay A', 'Mars': 'Mars exchange'}
    fig, ax = plt.subplots(figsize=(6.15, 3.1))
    for n in lanes:
        ax.axhline(y[n], color='#dddddd', lw=1, zorder=0)
        ax.text(-0.05, y[n], n, ha='right', va='center')
    kind_col = dict(SYN='#bbbbbb', SYNACK='#bbbbbb', ACK='#bbbbbb', DATA=C['earth'], DACK='#bbbbbb',
                    RCPT='#e0e0e0')
    data_labels = []
    for r in w.net.launches:
        te, ta, a, b, kind, pid, sid, k, d, p, lost, killed, logical = r
        if kind == 'RCPT':
            continue
        col = kind_col.get(kind, C['grey'])
        lw = 2.0 if kind == 'DATA' else 0.8
        ax.annotate('', xy=(ta / H, y[node_lane[b]]), xytext=(te / H, y[node_lane[a]]),
                    arrowprops=dict(arrowstyle='-|>', color=col, lw=lw, shrinkA=0, shrinkB=0, mutation_scale=8))
    for r in w.direct_log:
        ax.annotate('', xy=(r['ta'] / H, y['Mars exchange']), xytext=(r['te'] / H, y['Alice (Earth)']),
                    arrowprops=dict(arrowstyle='-|>', color=C['direct'], lw=1.2, ls='--', mutation_scale=8))
    marks = [(0.0003, 'Alice (Earth)', 'fund $100k\n(local)', 'left'),
             (1.6966, 'Mars exchange', 'import\n+$100k', 'right'),
             (2.2622, 'Earth exchange', 'RECEIVED\nknown', 'right'),
             (2.5024, 'Mars exchange', 'fill 1,000\n@ $100', 'left'),
             (3.0674, 'Earth exchange', 'shares\nimported', 'left')]
    for t, lane, txt, side in marks:
        ax.plot([t], [y[lane]], 'o', color=C['ink'], ms=4, zorder=5)
        ax.text(t + (0.05 if side == 'left' else -0.05), y[lane] + 0.18, txt, ha='left' if side == 'left' else 'right',
                va='bottom', fontsize=10)
    ax.plot([2.5024], [y['Bob (Mars)']], 'o', color=C['mars'], ms=4)
    ax.text(2.55, y['Bob (Mars)'] + 0.15, 'Bob: +$100k spendable at fill', va='bottom')
    ax.set_xlim(0, 3.75)
    ax.set_ylim(-0.4, len(lanes) - 0.35)
    ax.set_yticks([])
    ax.spines['left'].set_visible(False)
    ax.set_xlabel('hours after scenario start (no-loss trace, epoch 2026-09-22)')
    from matplotlib.lines import Line2D
    ax.legend(handles=[Line2D([], [], color=C['earth'], lw=2, label='backbone data (TRANSFER / RECEIVED)'),
                       Line2D([], [], color='#bbbbbb', lw=1, label='handshake / transport ACK'),
                       Line2D([], [], color=C['direct'], lw=1.2, ls='--', label='direct order copies')],
              loc='upper center', bbox_to_anchor=(0.5, -0.22), ncol=2, frameon=False, handlelength=1.8)
    save(fig, 'swimlane_s1a')


# ---------------------------------------------------------------- Figure: futures balances
def futures_series(path):
    import protocol
    series = []
    orig = protocol.World.audit

    def hooked(self):
        orig(self)
        series.append((self.now, account_state(self)))
    protocol.World.audit = hooked
    try:
        w, tr = run([(futures, dict(path=path))], until_h=340)
    finally:
        protocol.World.audit = orig
    series.append((w.now, account_state(w)))
    return series, tr.rel()


def fig_futures():
    fig, axs = plt.subplots(1, 2, figsize=(6.5, 2.9), sharey=True)
    for ax, path in zip(axs, ('rising', 'falling')):
        s, times = futures_series(path)
        ts = np.array([t / H for t, _ in s])
        for who, col, ls in (('Alice', C['alice'], (0, (5, 2))), ('Cara', C['cara'], (0, (1, 1.5)))):
            home = np.array([d[who]['home'] for _, d in s]) / 1000
            mars = np.array([(d[who]['remote'] + d[who]['held'] + d[who]['escrow']) for _, d in s]) / 1000
            ax.step(ts, home, where='post', color=col, lw=1.8, label=f'{who}: cash at home')
            ax.step(ts, mars, where='post', color=col, lw=1.6, ls=ls, label=f'{who}: cash at Mars (margin)')
        ax.axvspan(times['F1:open'], times['F1:maturity'], color='#f6e6e1', zorder=0)
        ax.axvspan(times['F1:maturity'], times['F1:discharge'], color='#fbf3e6', zorder=0)
        ax.set_title('rising: 110, 120, 130, 135, 125' if path == 'rising' else 'falling: 90, 80, 70, 65, 75',
                     loc='left')
        ax.set_xlabel('hours after start')
        ax.set_xlim(-5, 340)
        ax.set_ylim(-5, 215)
        ax.set_xticks([0, 100, 200, 300])
        ax.text(150, 108, 'contract open\n$160k in escrow', ha='center', color=C['escrow'])
    axs[0].set_ylabel('NeoDollars (thousands)')
    h, l = axs[0].get_legend_handles_labels()
    fig.legend(h, l, loc='lower center', ncol=2, frameon=False, bbox_to_anchor=(0.5, -0.02))
    fig.subplots_adjust(bottom=0.36, wspace=0.08, top=0.9)
    save(fig, 'futures_balances')


# ---------------------------------------------------------------- Figure: orbit / architecture map
def fig_map():
    """Top view at the epoch: inner system (linear) and the whole system (linear, 32 AU)."""
    from geom import _EL
    fig, axs = plt.subplots(1, 2, figsize=(6.5, 2.9), gridspec_kw=dict(width_ratios=[1.25, 1]))
    roles = {'Earth': 'Terra market', 'Mars': 'Ares market\n+ futures host', 'Ceres': 'Belt market'}
    p = {n: np.array(pos(n, 0.0)[:2]) for n in NODES}
    for k, ax in enumerate(axs):
        ax.set_aspect('equal')
        for n in NODES:
            P = 2 * math.pi / _EL[n]['n']
            xy = vpos(n, np.linspace(0, P, 800))[:, :2]
            ax.plot(*xy.T, color='#e4e4e4', lw=0.8, zorder=0)
        for s_ in SETTLEMENTS:
            for r in RELAYS:
                ax.plot([p[s_][0], p[r][0]], [p[s_][1], p[r][1]], color='#d3cde6', lw=0.7, zorder=1)
        ax.plot([p['Relay A'][0], p['Relay B'][0]], [p['Relay A'][1], p['Relay B'][1]], color=C['relay'], lw=1.6)
        ax.add_patch(plt.Circle((0, 0), 0.1, color='#f0b400', alpha=0.35, zorder=2))
        ax.plot([0], [0], 'o', color='#f0b400', ms=5 if k == 0 else 3, zorder=3)
        ax.set_xticks([]); ax.set_yticks([])
        for sp in ax.spines.values():
            sp.set_visible(False)
    inner = {'Mercury': (-6, -8), 'Venus': (6, -9), 'Earth': (6, 4), 'Mars': (-7, 2), 'Ceres': (6, 6),
             'Relay A': (6, -6), 'Relay B': (-6, -6), 'Jupiter': (6, 0)}
    outer = {'Jupiter': (-6, 5), 'Saturn': (4, -10), 'Uranus': (6, 0), 'Neptune': (-6, 8)}
    for ax, labels, lim in ((axs[0], inner, 3.05), (axs[1], outer, 31.5)):
        for n, (dx, dy) in labels.items():
            q = p[n]
            col = C['relay'] if n in RELAYS else (C['mars'] if n in roles else C['ink'])
            ax.plot(*q, 's' if n in RELAYS else 'o', color=col, ms=6 if (n in roles or n in RELAYS) else 4.5,
                    zorder=4)
            lab = n + (f"\n{roles[n]}" if (n in roles and ax is axs[0]) else '')
            ax.annotate(lab, q, xytext=(dx, dy), textcoords='offset points', ha='left' if dx > 0 else 'right',
                        va='center', color=col)
        ax.set_xlim(-lim, lim)
        ax.set_ylim((-1.0, 3.1) if ax is axs[0] else (-16, 31.5))
    axs[0].set_title('inner system', loc='left')
    axs[1].set_title('whole system to Neptune (30 AU)', loc='left')
    for n in ('Mercury', 'Venus', 'Earth', 'Mars', 'Ceres'):
        axs[1].plot(*p[n], 'o', color=C['mars'] if n in roles else C['ink'], ms=2, zorder=4)
    axs[1].annotate('inner system', (0, 1), xytext=(-40, -22), textcoords='offset points', color=C['grey'],
                    arrowprops=dict(arrowstyle='-', color=C['grey'], lw=0.6))
    fig.subplots_adjust(wspace=0.04, left=0.01, right=0.99, top=0.92, bottom=0.01)
    save(fig, 'map')


# ---------------------------------------------------------------- Appendix A1: completion CDFs
def fig_cdf():
    e2 = json.loads((R / 'e2.json').read_text())
    fig, axs = plt.subplots(1, 2, figsize=(5.3, 2.1), gridspec_kw=dict(width_ratios=[1.2, 1]))
    cols = dict(S1a=C['mars'], S1b=C['ceres'], S1c=C['earth'], S1d=C['relay'], S1e=C['direct'])
    def ecdf(k):
        x = np.sort([c for c in e2[k]['comps'] if c is not None])
        return np.r_[x[0], x], np.r_[0, np.arange(1, len(x) + 1) / len(e2[k]['comps'])]
    for k in ('S1a', 'S1b', 'S1c'):
        x, y = ecdf(k)
        axs[0].step(x, y, where='post', color=cols[k], label=k)
    axs[0].set_xscale('log'); axs[0].set_xlabel('hours to completion (log)'); axs[0].set_ylabel('P(done by t)')
    axs[0].legend(frameon=False, loc='lower right'); axs[0].set_title('Equity trades', loc='left')
    for k, ls in (('S1d', '-'), ('S1e', (0, (3, 2)))):
        x, y = ecdf(k)
        axs[1].step(x, y, where='post', color=cols[k], label=k, ls=ls)
    axs[1].set_xlabel('hours to completion'); axs[1].legend(frameon=False, loc='lower right')
    axs[1].set_title('Futures (both payouts home)', loc='left'); axs[1].set_yticklabels([])
    for a in axs:
        a.set_ylim(0, 1.02); a.grid(alpha=0.25, lw=0.5)
    fig.tight_layout(w_pad=0.6)
    save(fig, 'cdf')


# ---------------------------------------------------------------- Appendix A2: S2 incident search
def fig_s2():
    fig, axs = plt.subplots(1, 3, figsize=(5.6, 2.0), sharey=True)
    d = json.loads((R / 's2_search_rising.json').read_text())
    kinds = [('isolation', 'Isolation 72 h'), ('forced_loss', 'Forced loss 6 h'), ('reset', 'Endpoint reset')]
    pal = dict(Earth=C['earth'], Mars=C['mars'], Ceres=C['ceres'])
    for ax, (kd, title) in zip(axs, kinds):
        by = {}
        for r in d['runs']:
            if r['kind'] == kd:
                by.setdefault(r['node'], []).append((r['start'], min(r['damage'], 200)))
        for node, pts in by.items():
            pts.sort()
            x, y = zip(*pts)
            ax.plot(x, y, lw=1.6 if node in pal else 0.6, color=pal.get(node, '#bbbbbb'),
                    label=node if node in pal else None, zorder=3 if node in pal else 1)
        ax.set_title(title, loc='left'); ax.set_xlabel('incident start (h)'); ax.grid(alpha=0.25, lw=0.5)
        ax.set_xlim(0, 420)
    axs[0].set_ylabel('extra hours')
    axs[2].legend(frameon=False, loc='upper right')
    fig.tight_layout(w_pad=0.4)
    save(fig, 's2_search')


if __name__ == '__main__':
    which = sys.argv[1:] or ['swimlane', 'futures']
    for k in which:
        globals()['fig_' + k]()
        print(k)
