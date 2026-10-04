"""Split the generated evidence_appendix.tex into the scored appendix and its supplement.

    python build.py             # regenerates evidence_appendix.tex from ../results
    python split_appendix.py    # writes appendix_short.tex and supplement.tex, then runs pdflatex on both

appendix_short.tex keeps the sections of the teammate's 12-page condensation (shortened_appendix.tex) with current
data, plus what the brief requires and the design paper cites (S1 capital measures and traces, S3, E3 opening sheet
and settlement moments).  E6 and E7 go to the supplement whole.  Everything else goes to supplement.tex, whose tables are
numbered B1, B2, ...  References from one document to the other's tables are written as literal numbers ("Table B6"):
the script compiles both once, reads the numbers from the .aux files and substitutes them, so each .tex compiles on its
own (on Overleaf too).  After hand edits that add or remove tables, rerun the script or check those numbers.

appendix_short.tex is meant to be trimmed by hand afterwards.  The script will not overwrite it once it differs
from what the script last wrote, unless run with --force.
"""
import hashlib, re, subprocess, sys
from pathlib import Path

HERE = Path(__file__).parent
SHORT, SUPP = 'appendix_short', 'supplement'
STAMP = HERE / '.appendix_short.sha256'
SUPP_LINK = r'\doclink{supplement.pdf}{\texttt{supplement.pdf}}'


def chunks(body):
    """Cut the body at every section, paragraph, float, longtable and page break."""
    start = re.compile(r'^(\\section\*\{|\\paragraph\{|\\begin\{table\}|\\begin\{figure\}|\{\\tablefont|\\clearpage)')
    out, cur = [], []
    for ln in body.split('\n'):
        if start.match(ln) and cur:
            out.append('\n'.join(cur))
            cur = []
        cur.append(ln)
    out.append('\n'.join(cur))
    return out


def key(c):
    """A chunk's name: the label of a float, otherwise 'SEC <title>' or 'P <title>'."""
    m = re.match(r'\\section\*\{([^}]*)\}', c)
    if m:
        return 'SEC ' + m.group(1)
    m = re.match(r'\\paragraph\{([^}]*)\}', c)
    if m:
        return 'P ' + m.group(1)
    m = re.search(r'\\label\{([^}]*)\}', c)
    if m:
        return m.group(1)
    return c.strip()


# Chunks that go to the supplement, grouped under the supplement's own section headings (in this order).
SUPPLEMENT = [
    (None, None, ['SEC F. Message formats and sizes', 'tab:fcommon', 'tab:fbody', 'tab:fpkt', 'tab:fcap',
                  'P Packing and splitting rules.', 'P Examples.']),
    ('S1+. Efficiency per customer', None, ['P Per customer.', 'tab:s1cust']),
    (None, None, ['SEC T. Complete traces', 'tab:trS1a', 'tab:trS1b', 'tab:trS1c', 'tab:trS1d', 'tab:trS1e',
                  'tab:trS1f', 'tab:trS1g', 'tab:trS1h', 'tab:trS1i']),
    ('E2+. Every direct message, every backbone launch and every run under loss', None,
     ['tab:e2alldirect', 'tab:e2alllaunch', 'tab:e2sum', 'tab:e2allmc', 'fig:cdf']),
    (None, None, ['SEC E3+. State histories and settlement moments', 'tab:shS1a', 'tab:shS1b', 'tab:shS1c',
                  'tab:shS1d', 'tab:shS1e', 'tab:shS1f', 'tab:shS1g', 'tab:shS1i', 'P Settlement moments.',
                  'tab:e3moments']),
    ('S2+. Incident search and complete trace', None, ['fig:s2', 'P Complete trace of the incident.', 'tab:s2trace']),
    ('S3+. Complete relocation traces', None, ['P S3 relocations.', 'tab:trS3Ceres', 'tab:trS3Mercury',
                                               'tab:trS3Neptune']),
    ('E5+. Every direct leg at the shifted epochs', None, ['P Which path each instruction took.', 'tab:e5legs']),
]
# Everything from this section to the end (E6 quota and storage, E7 market data) moves to the supplement whole:
# the brief does not ask for either.
TAIL = 'SEC E6. Quota, backlog and storage'
# Supplement section headings dropped from the appendix (their remaining chunks stay where they are).
DROP = {'SEC E2+. Every message and every launch', 'tab:s1d', r'\clearpage'}     # S1d: complete trace in Section T, key steps in A

# Sentences in appendix chunks that point at material now in the supplement.
EDITS = [
    ('(complete traces of every run: Section T)', '(complete traces of every run: supplement, Section T)'),
    ('Section T\ngives the complete trace', 'Section T of the supplement\ngives the complete trace'),
    (r'Table~\ref{tab:e2alldirect} in Section E2+', r'Table~\ref{tab:e2alldirect} in the supplement'),
    (r'Table~\ref{tab:e2alldirect} lists every direct message', r'Table~\ref{tab:e2alldirect} in the supplement lists every direct message'),
    (r'Table~\ref{tab:e2alllaunch} in Section E2+', r'Table~\ref{tab:e2alllaunch} in the supplement'),
    (r'Table~\ref{tab:e2alllaunch} lists every backbone launch',
     r'Table~\ref{tab:e2alllaunch} in the supplement lists every backbone launch'),
    (r'Tables~\ref{tab:s1a} and~\ref{tab:s1d} give the financial traces of S1a and S1d. They omit rows',
     r'Table~\ref{tab:s1a} is an excerpt of the S1a trace and Table~\ref{tab:s1other} gives the key steps of the other runs; they omit rows'),
]

INTRO_ADD = (r"""
This appendix covers items S1 to S3 and E1 to E5 of the brief. It holds every result these items require. Tables numbered B are in the
supplement (""" + SUPP_LINK + r"""), which adds detail only: the complete seven-column trace of every S1 run and S3
relocation, every direct message and backbone launch, the state history and settlement moments of every scenario,
the event trace of the S2 incident and every direct leg at the shifted epochs. Sections F (message formats and
sizes), E6 (quota, backlog and storage) and E7 (market data), which the design paper cites, are in the supplement.
""")

E3_ADD = (r"""
\paragraph{Opening sheet and history.} Table~\ref{tab:e3open} is the opening balance sheet. The supplement
(Section E3+) lists every change in every scenario's balances by account, asset and location, and
Table~\ref{tab:e3moments} there gives, for every obligation in every scenario, when it is created, discharged,
backed and spendable.
""")

S2_ADD = (r"""
\paragraph{Complete trace.} Table~\ref{tab:s2trace} in the supplement lists every event of the incident from hour 0
to the opening, including every ignored copy and every endpoint timeout.
""")

SUPP_INTRO = (r"""\section*{About this supplement}
This supplement to the evidence appendix (\texttt{appendix\_short.pdf}) holds the detail behind it: complete traces,
every launch and every ledger change. Its tables are numbered B; tables numbered A are in the appendix. Every result
comes from the same simulator runs as the appendix, and the machine-readable traces are in
\texttt{milestone2/traces/}.
""")


def preamble(src, title, num):
    head = src.split(r'\begin{document}', 1)[0]
    # a clickable link to the other PDF where hyperref is installed, plain text otherwise
    head = head.replace(r'\usepackage{url}', r'\usepackage{url}' + '\n' +
                        r'\IfFileExists{etoolbox.sty}{\usepackage[hidelinks]{hyperref}}{}' + '\n' +
                        r'\newcommand{\doclink}[2]{\ifdefined\href\href{#1}{#2}\else#2\fi}')
    head = head.replace('% Built by build.py from ../results/*.json.',
                        '% Built by split_appendix.py from evidence_appendix.tex (build.py, ../results/*.json).')
    return (head + r'\begin{document}' + '\n' +
            rf'\begin{{center}}{{\LARGE\bfseries {title}\par}}\vspace{{3pt}}{{\normalsize MultiPlanetary Exchange '
            r'System \quad$\cdot$\quad Milestone 2 \quad$\cdot$\quad Design v3\par}\end{center}' + '\n\n' +
            r'\linespread{0.95}\selectfont' + '\n' +
            rf'\renewcommand{{\thetable}}{{{num}\arabic{{table}}}}\renewcommand{{\thefigure}}{{{num}\arabic{{figure}}}}'
            + '\n')


# The S1a trace in the appendix keeps only the rows that move value; Table trS1a in the supplement has every row.
EXCERPT = ('Sell ', 'Funds own', 'Debits', 'Imports once', 'Sends ORDER', 'Fill ')


def excerpt(c):
    out = []
    for ln in c.split('\n'):
        cells = ln.split(' & ')
        if len(cells) == 7 and re.match(r'\d', ln) and not any(cells[3].startswith(x) for x in EXCERPT):
            continue
        out.append(ln)
    c = '\n'.join(out)
    return c.replace(r'\caption{Full trace of S1a:', r'\caption{Excerpt of the S1a trace, the rows that move value '
                     r'(the complete trace, with the quote, admission and duplicate-copy rows, is Table~\ref{tab:trS1a}):')


def split(src):
    body = src.split(r'\begin{document}', 1)[1].rsplit(r'\end{document}', 1)[0]
    body = body[body.index(r'\section*{Introduction}'):]
    cs = chunks(body)
    by = {key(c): c for c in cs}
    to_supp = {k for _, _, ks in SUPPLEMENT for k in ks}
    tail = cs[[key(c) for c in cs].index(TAIL):]
    to_supp |= {key(c) for c in tail}
    missing = (to_supp | DROP) - set(by)
    assert not missing, f'chunks not found: {missing}'

    moved = ['tab:e3open']     # E3+ chunk kept in the appendix, after E3
    a = []
    for c in cs:
        k = key(c)
        if k in to_supp or k in DROP or k in moved:
            continue
        for old, new in EDITS:
            c = c.replace(old, new)
        if k == 'tab:s1a':
            c = excerpt(c)
        if k == 'SEC Introduction':
            c = c.rstrip() + '\n' + INTRO_ADD
        a.append(c)
        if k == 'tab:e3times':
            a += [E3_ADD] + [by[m] for m in moved]
        if k == 'tab:s2mc':
            a.append(S2_ADD)

    b = [SUPP_INTRO]
    for title, intro, ks in SUPPLEMENT:
        if title:
            b.append(rf'\section*{{{title}}}' + ('\n' + intro if intro else ''))
        b += [by[k] for k in ks]
    b += tail
    return '\n'.join(a), '\n'.join(b)


def pdflatex(name):
    r = subprocess.run(['pdflatex', '-interaction=nonstopmode', '-halt-on-error', f'{name}.tex'], cwd=HERE,
                       capture_output=True, text=True)
    if r.returncode:
        print(r.stdout[-3000:])
    return not r.returncode


def labels(name):
    aux = (HERE / f'{name}.aux').read_text()
    return dict(re.findall(r'\\newlabel\{([^}]*)\}\{\{([^}]*)\}', aux))


def cross_refs(tex, own, other):
    """Replace \\ref{x} for every label x defined only in the other document by its number there."""
    def sub(m):
        lab = m.group(1)
        if lab in own:
            return m.group(0)
        assert lab in other, f'undefined reference {lab}'
        return other[lab]
    return re.sub(r'\\ref\{([^}]*)\}', sub, tex)


def cleanup():
    for name in (SHORT, SUPP):
        for ext in ('aux', 'log', 'out'):
            (HERE / f'{name}.{ext}').unlink(missing_ok=True)


if __name__ == '__main__':
    src = (HERE / 'evidence_appendix.tex').read_text()
    a, b = split(src)
    short_tex = preamble(src, 'Evidence Appendix', 'A') + a + '\n\\end{document}\n'
    supp_tex = preamble(src, 'Evidence Appendix: Supplement', 'B') + b + '\n\\end{document}\n'
    out = HERE / f'{SHORT}.tex'
    if out.exists() and '--force' not in sys.argv:
        old = hashlib.sha256(out.read_bytes()).hexdigest()
        if not STAMP.exists() or STAMP.read_text().strip() != old:
            sys.exit(f'{out.name} was edited by hand; rerun with --force to overwrite it')
    # pass 1: number each document's own tables; pass 2: write the other document's numbers in literally
    out.write_text(short_tex)
    (HERE / f'{SUPP}.tex').write_text(supp_tex)
    ok = pdflatex(SHORT) and pdflatex(SUPP)
    if ok:
        la, lb = labels(SHORT), labels(SUPP)
        short_tex, supp_tex = cross_refs(short_tex, la, lb), cross_refs(supp_tex, lb, la)
        out.write_text(short_tex)
        (HERE / f'{SUPP}.tex').write_text(supp_tex)
        ok = all(pdflatex(n) for n in (SHORT, SUPP, SHORT, SUPP))
    STAMP.write_text(hashlib.sha256(short_tex.encode()).hexdigest())
    cleanup()
    print('pdf' if ok else 'tex only (pdflatex failed)')
