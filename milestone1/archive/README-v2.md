# Milestone 1 — current design version 2

Start with [SIMPLIFICATION.md](SIMPLIFICATION.md) for a plain-English account of the changes, the Earth–Mars and Earth–Ceres examples, packet counts and a reading guide.

[DESIGN.md](DESIGN.md) is the authoritative current system specification. It replaces the two-clearinghouse architecture with direct settlement between planetary exchanges, exact single-use reservations, atomic local ledger operations and explicitly funded transfers. It includes the requirements mapping, failure rules, later-price contract, quotas and long-horizon policy.

[IMPLEMENTATION.md](IMPLEMENTATION.md) defines the remaining Milestone 2 simulation and evidence acceptance checks. The current work is a detailed design and limited executable evidence, not the completed paper or full stochastic simulator.

## Reproduce the current evidence

Python 3 and NumPy are required. Run from the repository root:

```sh
python3 milestone1/checks_v2.py
```

This runs geometry/access calculations, 27 financial tests, bounded state exploration, four conditional no-loss packet traces, accounting checks and a provenance manifest. It does not rerun the expensive long scan. To regenerate the existing 200-year hourly screening separately:

```sh
python3 milestone1/model.py --scan
```

Original files under `info/` are not modified. See [results/README.md](results/README.md) for the distinction between current results, shared geometry and historical evidence.

## Evidence scope

The current financial model is `direct_settlement.py`; its tests are `test_direct_settlement.py`. `trace_v2.py` uses `transport_no_loss.py` for cold-session, unbatched traces. These check source debits, duplicate-safe imports and funded in-transit value, but do not implement the full lossy transport or the derivative's complete packet execution.

The baseline deliberately uses all-or-none orders and full maximum-loss collateral. Partial fills, arbitrary distributed baskets and protection against malicious operators are outside its claims.

## Historical material

`archive/DESIGN-v1.md` and `archive/IMPLEMENTATION-v1.md` preserve the previous design. `archive/settlement-v2-interrupted-draft.py` is an abandoned intermediate proposal, not the current model. Root scripts `verify.py`, `checks.py` and `third_site_example.py` reproduce historical clearinghouse evidence only; use `checks_v2.py` for the current design.
