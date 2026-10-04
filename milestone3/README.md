# Milestone 3: MPX Orrery

MPX Orrery is an interactive website for the MultiPlanetary Exchange System. It replays every required scenario on a live orrery and lets you build your own. Custom scenarios run the **same Python simulator** as the Milestone 2 papers, inside the browser through Pyodide.

```bash
python3 -m http.server 8765
```

Run this from the repository root, then open http://localhost:8765 (it redirects to the orrery). Serving the root rather than this folder lets the paper links in the header reach `../paper/`. The same files are published at https://lmesh91.github.io/gqh-2026/.

## What it does

- **Scenario library (20 presets)**
  - S1a–S1i
  - The S2 worst-case incident, with and without restart notice (A1)
  - Mars isolation at fixing
  - A lossy run
  - S3 relocations (Neptune, Mercury, Dax long from Neptune)
  - E5: the 2028 Mars blackout with forwarding (rule R9) and with R9 switched off, and the same trade in 2126
- **Orrery**
  - Planets and relays on their Kepler orbits.
  - Every backbone hop and direct copy flies from the sender's position at emission to the receiver's position at arrival.
  - Lost and killed packets, blocked links, maintenance windows and incidents are all shown.
  - Three scales: whole system (log), inner system, and true scale.
- **Ledger panel**
  - Each account's cash split into spendable at home, free at host, held for orders, contract margin and in transit. Share positions are shown too.
  - Updated after every ledger event.
- **Timeline**
  - Data packets, direct packets, key moments and incidents. Click or drag to jump.
  - "Skip quiet stretches" fast-forwards idle hours, so a 330-hour futures contract still plays in about a minute.
- **Build your own**
  - Up to four trades: share purchases, capped futures, or repeat trading.
  - Move any account to any settlement and change the start date (up to 100,000 years ahead, with a shortcut to the 2028 Mars blackout).
  - Random loss and seed, maintenance on or off, and incidents (isolation, forced loss, endpoint reset).
  - Switch rule R9 (forwarding) off for comparison, toggle alternative A1, the application backoff, the direct-copy cap and the fallback slack.
- **Trace tab**
  - The brief's seven-column trace, synced to the playhead.
- **Packets tab**
  - Every launch with its fate, plus the courier's session, failure and resubmission events.
- **Monte Carlo tab**
  - 100–1,000 lossy repeats of any scenario, run in the browser. Thirty runs take about half a second.
  - Overlaid on the appendix's 2,000-run result where one exists.
- **Evidence tab**
  - S3 access, the S2 incident search, E5 epochs and the E4 200-year direct-path closures.

## Files

| File | Purpose |
|---|---|
| `app.html` | The page itself, used as-is for the published Artifact |
| `index.html` | `app.html` wrapped in a document skeleton for local serving. Generated |
| `engine.js` | Web Worker that boots Pyodide and runs `webapi.py` |
| `py/webapi.py` | Bridge: scenario config → replay (packets, events, account states, trace, metrics) and Monte Carlo |
| `build_site.py` | Bundles the simulator sources, pre-computes the presets and extracts the evidence summaries into `data/` |
| `pyodide/` | Pyodide 0.27.7 core runtime (MPL-2.0), vendored so the site works offline and inside the Artifact sandbox |

After changing the simulator or `app.html`, rebuild:

```bash
python milestone3/build_site.py
```

Presets are pre-computed, so they also play when the Python engine cannot start.
