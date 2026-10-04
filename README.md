# A Safe and Reliable MultiPlanetary Exchange System

A prefunded design for trading equities and a capped futures contract across nine settlements, from Mercury to Neptune, where messages take minutes to hours, packets are lost and the Sun can block a path for weeks. Each exchange acts only on assets already in its own ledger and each balance has exactly one writer, so loss, delay and duplication can slow service but cannot create, destroy or double-spend value.

## Read the paper

| File | What it is |
|---|---|
| [`paper/design_paper.pdf`](paper/design_paper.pdf) | The design paper (12 pages) |
| [`paper/evidence_appendix.pdf`](paper/evidence_appendix.pdf) | The evidence appendix: traces, calculations and simulation results for items S1–S3 and E1–E5 (12 pages) |
| [`paper/supplement.pdf`](paper/supplement.pdf) | The supplement: complete traces, message formats, quota/backlog/storage and market data (51 pages) |

The `.tex` sources are next to the PDFs and compile with a base TeX Live install (`pdflatex`).

## Explore the simulator

**[MPX Orrery](https://lmesh91.github.io/gqh-2026/)** replays every scenario in the paper on a live model of the solar system and lets you build your own. It runs the paper's simulator in your browser. To run it locally, serve the repository root (`python3 -m http.server 8765`) and open http://localhost:8765.

## Repository layout

| Folder | Contents |
|---|---|
| [`paper/`](paper) | The final submission (TeX and PDF) |
| [`milestone1/`](milestone1) | Early design exploration and prototypes |
| [`milestone2/`](milestone2) | The discrete-event simulator, the evidence pipeline, results and traces, and the papers as generated before manual editing. Reads the hackathon data in `info/data.zip` |
| [`milestone3/`](milestone3) | MPX Orrery, an interactive website that replays every scenario and runs the same simulator in the browser |

Every number in the papers is produced by the simulator in `milestone2/`; see [`milestone2/README.md`](milestone2/README.md) to reproduce them.
