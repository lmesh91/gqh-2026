# Evidence index

## Current design version 3

- `v3_safety_checks.json`: 23 bounded ledger/payoff tests, six serial fill/cancel/withdrawal permutations, fixed-width packing arithmetic. Not a full protocol proof.
- `v3_account_example.csv`: $10,000 prefunding, two orders, partial fill, cancellation and $6,000 withdrawal, with conserved totals after each event. This is a two-account subset example, not the six-account S1 evidence.
- `v3_provenance.json`: current document/model/test hashes and source brief/data hashes.

No v3 packet-level timing, stochastic recovery, full derivative execution or long-horizon financial simulation is claimed here. V2 timings cannot be relabeled as v3. Milestone 2 results in their separate directory must state which application version they actually execute.

## Historical design version 2

- `v2_earth_mars_*`: direct Earth–Mars trade, original opening accounts.
- `v2_earth_ceres_*`: direct Earth–Ceres trade; no Mars intermediary.
- `v2_jupiter_mars_*`, `v2_neptune_mars_*`: declared relocation of Alice and her existing assets for access comparisons.
- Each family contains financial events, compact conserved balances, application messages, physical packets and a summary. Balances group unaffected accounts; these files are not yet the full account-by-account E3 appendix.
- `v2_comparison.json`: historical versus current no-loss examples.
- `v2_safety_checks.json`: bounded financial checks, not a general proof or full transport test.
- `v2_regression_checks.json`: packet totals, quota allocation and per-event balance assertions.
- `v2_provenance.json`: hashes and scope for current inputs, implementation and outputs at the latest validation run.

The four traces assume no random losses, no batching and a cold session established after the order arrives. They execute geometry and transport controls, but do not establish stress-case or stochastic completion probabilities. Warm-session counts in the design are structural estimates.

## Shared geometry

`validation.json`, `access.csv`, `long_scan_links.csv`, `long_scan_routes_screen.csv`, `long_scan_boundary.json`, `difficult_epoch.json` use the supplied frozen orbital elements. Access now includes Earth, Mars, Ceres and Neptune destinations. The long scan is an hourly screening, with one refined boundary and a separately re-evaluated difficult route; it is not a certified continuous-time availability envelope.

## Historical results — do not use as current settlement evidence

All unprefixed `trade_*`, `earth_ceres_*`, `safety_checks.json`, `regression_checks.json` and `failure_recovery_states.csv` concern the original clearinghouse model. `placement_screen.json` screens the old two-authority placement problem; it does not justify the current asset-market locations.

`hop_probability.json` and `forced_loss_hop_probes.json` are isolated historical transport probes, not whole-trade reliability measurements. `provenance.json` is the historical manifest and may refer to earlier script hashes. Preserve these results for comparison; current bounded financial output is prefixed `v3_`; v2 traces remain historical.
