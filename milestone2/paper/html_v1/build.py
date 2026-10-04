"""Build the design paper and the evidence appendix from the simulator results.

    python build.py            # HTML + PDF (needs google-chrome for printing)

Every number in either document is read from ../results/*.json or recomputed here from the
simulator (traces), so re-running the evidence scripts and this file regenerates both papers."""
import json, math, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RES = HERE.parent / 'results'
sys.path.insert(0, str(HERE.parent / 'sim'))


def load(name):
    p = RES / f'{name}.json'
    return json.loads(p.read_text()) if p.exists() else None


S1, E1, E2, S3, E5, X, PL = (load(n) for n in ('s1', 'e1', 'e2', 's3', 'e5', 'extras', 'placement'))
E4 = load('e4_scan')
S2D = load('s2_detail')
S2R, S2F = load('s2_search_rising'), load('s2_search_falling')


# ------------------------------------------------------------------ formatting helpers
def h(x, d=2):
    return '—' if x is None or (isinstance(x, float) and not math.isfinite(x)) else f'{x:,.{d}f}'


def money(v):
    return f'${v:,.0f}'


def pct(x, d=1):
    return f'{100 * x:.{d}f}%'


def prob(p):
    if p >= 0.9999:
        return f'1 − {1 - p:.1e}' if p < 1 else '1'
    return f'{p:.4f}'


def table(head, rows, cls='', num=()):
    th = ''.join(f'<th class="n">{c}</th>' if i in num else f'<th>{c}</th>' for i, c in enumerate(head))
    body = []
    for r in rows:
        if isinstance(r, str):
            body.append(f'<tr class="group"><td colspan="{len(head)}">{r}</td></tr>')
            continue
        body.append('<tr>' + ''.join(f'<td class="n">{c}</td>' if i in num else f'<td>{c}</td>'
                                     for i, c in enumerate(r)) + '</tr>')
    return f'<table class="{cls}"><thead><tr>{th}</tr></thead><tbody>{"".join(body)}</tbody></table>'


def fig(name, cap, width='100%'):
    return f'<figure><img src="figs/{name}.svg" style="width:{width}"><figcaption>{cap}</figcaption></figure>'


def doc(title, body):
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{title}</title>
<link rel="stylesheet" href="style.css"></head><body>{body}</body></html>'''


def print_pdf(html, pdf):
    for exe in ('google-chrome', 'google-chrome-stable', 'chromium'):
        try:
            subprocess.run([exe, '--headless=new', '--no-sandbox', '--disable-gpu', '--no-pdf-header-footer',
                            f'--print-to-pdf={pdf}', html.as_uri()], check=True, capture_output=True, timeout=180)
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
    return False


if __name__ == '__main__':
    import paper_text, appendix_text
    out = {'design_paper': paper_text.build(), 'evidence_appendix': appendix_text.build()}
    for name, body in out.items():
        f = HERE / f'{name}.html'
        f.write_text(doc(name.replace('_', ' ').title(), body))
        ok = print_pdf(f, HERE / f'{name}.pdf')
        print(name, 'pdf' if ok else 'html only')
