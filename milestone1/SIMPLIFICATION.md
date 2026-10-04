# Version 3: prefunded trading accounts

This is the plain-English guide to the current [DESIGN.md](DESIGN.md). Version 2 is preserved in `archive/`; the per-order home-reservation protocol is no longer the baseline.

Alice now funds a trading account on Mars, then trades against that local account. Earth does not approve every fill. Mars reserves available cash for orders, executes partial fills, releases cancelled quantities and credits proceeds using one authoritative local ledger.

## What changes

| Version 2 | Version 3 |
|---|---|
| Earth reserves cash for one exact order | Earth transfers a chosen amount to Alice's Mars account |
| Mars asks Earth to pay for a provisional match | Mars admits orders only against balances already credited locally |
| All-or-none purchase against one counterparty | Partial fills across counterparties, with price-time priority |
| Cash cannot be reused through the same reservation | Available proceeds and released holds can fund another host order |
| Source payment and stock delivery are separate trade stages | Cash and shares exchange atomically at the host |
| Home delivery follows the one-off trade | Client chooses automatic home withdrawal or retention for further trading |

Local holds still exist. What disappears is a **remote, order-specific authorization**. Without local order holds, multiple orders could still spend the same trading balance.

## Follow the money

Alice has $10,000 on Earth. Earth debits it into a uniquely identified transfer to her Mars account. Mars credits it once. If a screen calls it “locked on Earth,” that is a non-spendable memorandum; there is only one authoritative $10,000.

| Step | Alice available on Mars | Alice's order holds | Seller cash credited |
|---|---:|---:|---:|
| Funding imported | $10,000 | $0 | $0 |
| Two $4,000 orders accepted | $2,000 | $8,000 | $0 |
| First order partially fills for $1,500 at its limit | $2,000 | $6,500 | $1,500 |
| Second order cancelled | $6,000 | $2,500 | $1,500 |
| Alice withdraws the available $6,000 | $0 | $2,500 | $1,500 |

Alice also owns the shares acquired for $1,500. Until withdrawn they remain in her Mars account and can be traded there. After Earth imports the $6,000 return, that amount becomes available on Earth. The still-open order retains its $2,500 hold on Mars. The original $10,000 has not reappeared at both planets.

A fill at a better price releases the difference immediately. For example, 150 shares filled at $9 against a $10 limit consume $1,350 and release $150; the rest of the buy order remains backed at its limit price.

## What keeps it safe

Only Mars controls the spending of credited Mars balances. Each fill records both asset debits and credits atomically. A withdrawal debits available funds before exporting them, and the destination imports each export once. Message loss, repeated instructions and resets do not remove those records.

Earth cannot release an old “locked” amount because Alice asks or a timer expires. Mars may already have paid a seller. Returning money requires Mars to remove the **current available amount**, then send a new funded transfer. Order cancellation releases only unfilled holds at Mars; it does not return money to Earth.

If an order arrives before its funding, it is rejected, not automatically queued for later investment. Repeating the rejected ID returns the same result; a fresh order is needed after funding. If cancellation arrives before the order, a tombstone prevents the late order from starting. Cancel-and-new replaces amendments; changed terms never reuse the old identifier.

Closing an account freezes new activity and cancels remaining cancellable orders. Existing contract obligations remain funded until maturity. Late deposits into a closed generation must be imported into a restricted return balance and sent back, not ignored or silently made tradeable.

## Where the savings come from

Funding and withdrawals need backbone transfers. Host orders and fills do not need an Earth–Mars settlement conversation. Many fills can share one initial funding transfer and a final withdrawal.

This does not remove the direct-channel quota for Alice's remote commands or the exchange's replies. It also does not make Mars-held shares spendable on Earth. Under the brief, remote completion still waits for the intended home imports. The baseline simple purchase automatically withdraws each fill's shares; repeated-trading runs may retain balances and perform a final sweep, with the later home completion reported honestly.

A cold two-link funding transfer with its financial receipt costs 28 physical backbone transmissions and three originations. A later withdrawal on the same session costs 16 and two. Add a single direct buy instruction and the structural total can be 45, the same as the previous one-off trade. Client status, extra withdrawals, replies, retries and new sessions add cost. **The improvement is amortization across repeated trading, not a universal reduction for one purchase.** Version 2's measured completion times do not carry over.

## Futures fit the same account model

Alice and Cara fund their Mars accounts, then separately authorize margin holds. Each contributes the same $80,000 maximum-loss margin as before. That money cannot simultaneously back stock orders or withdrawals. A contract opens only when both instructions and full holds exist.

Unopened/expired instructions release margin to available Mars balances. They do not magically refund Earth or Ceres. The demonstrated contract automatically exports both final allocations home after fixing, preserving the brief's local-spendability requirement. The same $160,000 open-position escrow meets the 32% scale example; unused cash merely held at Mars does not count as an open position.

## What to read and hand to the other agent

1. DESIGN sections 1–3: authority, requirements, accounts and completion.
2. Sections 4–6: deposits, withdrawals, partial fills and failure rules.
3. Sections 7–9: quotas, futures and communication accounting.
4. Sections 10–13: evidence status and scenario requirements.
5. [IMPLEMENTATION.md](IMPLEMENTATION.md): migration checklist for Milestones 2–3.

The v3 bounded ledger has 23 passing tests, including all six serial orders of a fill/cancel/withdrawal race. `results/v3_account_example.csv` records the example above with conservation checks. These are financial checks, not a new full network simulator. The existing v2 timings and packet traces are explicitly historical. No Milestone 2–3 files were changed for this revision.
