"""Build the design paper and the evidence appendix (LaTeX) from the simulator results.

    python build.py            # writes design_paper.tex and evidence_appendix.tex, then runs pdflatex

Every number in either document is read from ../results/*.json or recomputed here from the
simulator (traces), so re-running the evidence scripts and this file regenerates both papers.
The .tex files use only packages from a base TeX Live install (texlive-latex-base)."""
import json, math, re, subprocess, sys
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


# ------------------------------------------------------------------ number formatting
def h(x, d=2):
    return '—' if x is None or (isinstance(x, float) and not math.isfinite(x)) else f'{x:,.{d}f}'


def money(v):
    return f'${v:,.0f}'


def pct(x, d=1):
    return f'{100 * x:.{d}f}%'


# ------------------------------------------------------------------ LaTeX helpers
class Raw(str):
    """Text that is already LaTeX and must not be escaped."""


_ESC = {'\\': r'\textbackslash{}', '&': r'\&', '%': r'\%', '$': r'\$', '#': r'\#', '_': r'\_',
        '{': r'\{', '}': r'\}', '~': r'\textasciitilde{}', '^': r'\textasciicircum{}'}


def esc(s):
    if isinstance(s, Raw):
        return s
    return ''.join(_ESC.get(c, c) for c in str(s))


def fill(text, env):
    """Replace every <<expr>> in a LaTeX template with the escaped value of expr."""
    return re.sub(r'<<(.+?)>>', lambda m: esc(eval(m.group(1), {**globals(), **env})), text, flags=re.S)


RULE_TOP = r'\noalign{\vskip 1pt}\hline\noalign{\vskip 1pt}'
RULE_MID = r'\hline\noalign{\vskip 1pt}'


def tabular(cols, head, rows, width=r'\linewidth'):
    """A tabularx with light rules. cols uses L (ragged), R (right) and l/r/c, or p{..}."""
    hd = ' & '.join(r'\textbf{' + esc(c) + '}' for c in head) + r' \\' + RULE_MID
    body = []
    for r in rows:
        if isinstance(r, str):          # group row
            body.append(r'\multicolumn{' + str(len(head)) + r'}{@{}l}{\textit{' + esc(r) + r'}} \\')
        else:
            body.append(' & '.join(esc(c) for c in r) + r' \\')
    return (r'\begin{tabularx}{' + width + '}{@{}' + cols + '@{}}' + RULE_TOP + hd + '\n' + '\n'.join(body) +
            r'\noalign{\vskip 1pt}\hline' + '\n' + r'\end{tabularx}')


def table(cols, head, rows, caption, label=None, pos='!htb', sep='4pt'):
    lab = r'\label{' + label + '}' if label else ''
    return (r'\begin{table}[' + pos + r']\centering\tablefont\setlength{\tabcolsep}{' + sep + '}' + '\n' + r'\caption{' + caption + '}' + lab + '\n' +
            tabular(cols, head, rows) + '\n' + r'\end{table}')


def longtab(cols, head, rows, caption, label=None, lw='4cm', sep='3pt'):
    """A longtable that may break across pages (traces).  longtable has no X columns, so L becomes a ragged
    paragraph column of width lw."""
    cols = cols.replace('L', r'>{\raggedright\arraybackslash}p{' + lw + '}')
    lab = r'\label{' + label + '}' if label else ''
    n = len(head)
    hd = ' & '.join(r'\textbf{' + esc(c) + '}' for c in head) + r' \\'
    body = '\n'.join(' & '.join(esc(c) for c in r) + r' \\' for r in rows)
    return ('{\\tablefont\\setlength{\\tabcolsep}{' + sep + '}\n\\begin{longtable}{@{}' + cols + '@{}}\n'
            r'\caption{' + caption + '}' + lab + r'\\' + RULE_TOP + hd + RULE_MID + r'\endfirsthead' + '\n' +
            r'\multicolumn{' + str(n) + r'}{@{}l}{\textit{(continued)}}\\' + RULE_TOP + hd + RULE_MID + r'\endhead' + '\n' +
            r'\hline\endfoot' + '\n' + body + '\n' + r'\end{longtable}}')


def fig(name, caption, label=None, pos='!htb'):
    """Figures are drawn at their printed size (figs.py), so they are never scaled and their text stays at 10 pt."""
    lab = r'\label{' + label + '}' if label else ''
    return (r'\begin{figure}[' + pos + r']\centering' + '\n' + r'\includegraphics{figs/' + name +
            '.pdf}\n' + r'\caption{' + caption + '}' + lab + '\n' + r'\end{figure}')


PREAMBLE = r'''\documentclass[@SIZE@,letterpaper]{article}
% Built by build.py from ../results/*.json. Needs only texlive-latex-base.
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{lmodern}
\usepackage{textcomp}
\usepackage[margin=1in]{geometry}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage{array,tabularx,longtable}
\usepackage{url}
\usepackage{fancyhdr}

% Characters that appear in data-driven text
\DeclareUnicodeCharacter{2192}{\ensuremath{\rightarrow}}
\DeclareUnicodeCharacter{2190}{\ensuremath{\leftarrow}}
\DeclareUnicodeCharacter{2264}{\ensuremath{\le}}
\DeclareUnicodeCharacter{2265}{\ensuremath{\ge}}
\DeclareUnicodeCharacter{2212}{\ensuremath{-}}
\DeclareUnicodeCharacter{2248}{\ensuremath{\approx}}
\DeclareUnicodeCharacter{0394}{\ensuremath{\Delta}}
\DeclareUnicodeCharacter{2032}{\ensuremath{'}}
\DeclareUnicodeCharacter{220F}{\ensuremath{\prod}}
\DeclareUnicodeCharacter{207B}{\ensuremath{^{-}}}
\DeclareUnicodeCharacter{2070}{\ensuremath{^{0}}}
\DeclareUnicodeCharacter{00B9}{\ensuremath{^{1}}}
\DeclareUnicodeCharacter{2074}{\ensuremath{^{4}}}
\DeclareUnicodeCharacter{2075}{\ensuremath{^{5}}}
\DeclareUnicodeCharacter{2080}{\ensuremath{_{0}}}
\DeclareUnicodeCharacter{1D62}{\ensuremath{_{i}}}
\DeclareUnicodeCharacter{00B2}{\ensuremath{^{2}}}
\DeclareUnicodeCharacter{00B3}{\ensuremath{^{3}}}
\DeclareUnicodeCharacter{2076}{\ensuremath{^{6}}}
\DeclareUnicodeCharacter{2077}{\ensuremath{^{7}}}
\DeclareUnicodeCharacter{2078}{\ensuremath{^{8}}}
\DeclareUnicodeCharacter{2079}{\ensuremath{^{9}}}
\DeclareUnicodeCharacter{2081}{\ensuremath{_{1}}}
\DeclareUnicodeCharacter{2082}{\ensuremath{_{2}}}
\DeclareUnicodeCharacter{2083}{\ensuremath{_{3}}}
\DeclareUnicodeCharacter{2084}{\ensuremath{_{4}}}
\DeclareUnicodeCharacter{2085}{\ensuremath{_{5}}}
\DeclareUnicodeCharacter{2086}{\ensuremath{_{6}}}
\DeclareUnicodeCharacter{2087}{\ensuremath{_{7}}}
\DeclareUnicodeCharacter{2088}{\ensuremath{_{8}}}
\DeclareUnicodeCharacter{2089}{\ensuremath{_{9}}}

\setlength{\extrarowheight}{0.5pt}
\newcolumntype{L}{>{\raggedright\arraybackslash}X}
\newcolumntype{R}{>{\raggedleft\arraybackslash}X}
\setlength{\parskip}{2pt plus 1pt}
\setlength{\parindent}{0pt}
\setlength{\textfloatsep}{8pt plus 2pt minus 2pt}
\setlength{\floatsep}{8pt plus 2pt minus 2pt}
\setlength{\intextsep}{8pt plus 2pt minus 2pt}
\setlength{\abovecaptionskip}{3pt}
\setlength{\belowcaptionskip}{3pt}
\renewcommand{\topfraction}{0.9}
\renewcommand{\bottomfraction}{0.8}
\renewcommand{\textfraction}{0.07}
\renewcommand{\floatpagefraction}{0.85}
\setcounter{topnumber}{3}
\setcounter{bottomnumber}{2}
\setcounter{totalnumber}{4}
\setlength{\LTpre}{4pt}
\setlength{\LTpost}{4pt}
\AtBeginDocument{\setlength{\LTcapwidth}{\textwidth}}
\makeatletter
% compact section headings
\renewcommand\section{\@startsection{section}{1}{\z@}{-9pt plus -2pt minus -1pt}{3pt}{\normalfont\large\bfseries}}
\renewcommand\subsection{\@startsection{subsection}{2}{\z@}{-6pt plus -2pt minus -1pt}{2pt}{\normalfont\normalsize\bfseries}}
\renewcommand\paragraph{\@startsection{paragraph}{4}{\z@}{4pt plus 1pt}{-0.6em}{\normalfont\normalsize\bfseries}}
\makeatother
\pagestyle{plain}
'''


def document(title, subtitle, body, abstract=None, size='11pt'):
    # Tables use 10 pt in both documents: small at 11 pt, normalsize at 10 pt.
    tf = r'\newcommand{\tablefont}{' + (r'\small' if size == '11pt' else r'\normalsize') + '}' + '\n'
    head = (PREAMBLE.replace('@SIZE@', size) + tf + r'\begin{document}' + '\n' +
            r'\begin{center}{\LARGE\bfseries ' + title + r'\par}\vspace{3pt}{\normalsize ' + subtitle +
            r'\par}\end{center}' + '\n')
    if abstract:
        head += (r'\begin{center}\textbf{Abstract}\end{center}\vspace{-6pt}\begin{quote}' + '\n' + abstract + '\n' +
                 r'\end{quote}' + '\n')     # article's abstract sets its heading in 9 pt
    return head + body + '\n' + r'\end{document}' + '\n'


def compile_pdf(name):
    for _ in range(2):          # second pass resolves cross-references
        r = subprocess.run(['pdflatex', '-interaction=nonstopmode', '-halt-on-error', f'{name}.tex'], cwd=HERE,
                           capture_output=True, text=True)
        if r.returncode:
            print(r.stdout[-3000:])
            return False
    for ext in ('aux', 'log', 'out'):
        (HERE / f'{name}.{ext}').unlink(missing_ok=True)
    return True


if __name__ == '__main__':
    import paper_text, appendix_text
    # design_paper.tex is now edited by hand: regenerate it from paper_text.py only when asked explicitly
    out = {'evidence_appendix': appendix_text.build()}
    if 'paper' in sys.argv[1:]:
        out['design_paper'] = paper_text.build()
    for name, tex in out.items():
        (HERE / f'{name}.tex').write_text(tex)
        print(name, 'pdf' if compile_pdf(name) else 'tex only (pdflatex failed)')
