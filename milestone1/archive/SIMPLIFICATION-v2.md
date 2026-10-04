# What changed in Milestone 1

Read this first, then the numbered sections of [DESIGN.md](DESIGN.md). Version 2 implements the direct exchange-to-exchange settlement proposal. The original documents remain in `archive/` for comparison.

## The architectural change

A planetary exchange now runs its local markets and settles their trades. Mars runs Ares Habitat; Ceres runs Belt Works; Earth runs Terra Fabrication. There is no compulsory trip through a separate Mars or Neptune clearinghouse. The nine exchanges fit within the brief's twelve-institution limit.

For Alice's purchase of Belt Works, Earth holds Alice's cash and Ceres holds the seller's inventory. Earth and Ceres settle directly. Mars has no role. Geography and institutional independence are separate choices: a local independent clearer could be added, but it is not required by the baseline. The brief assumes honest institutions; this design does not claim protection against an exchange deliberately fabricating ledger evidence. Separating organizations would require a new trust, custody and verification design rather than merely renaming one process.

Keeping asset markets local also avoids moving inventory to a hub before a sale and returning proceeds afterward. Centralizing all markets remains possible, but these transfers must be charged. The old placement comparison is no longer a recommendation for two clearinghouses.

## Follow one purchase

1. Alice reserves $100,000 at Earth for one exact order on Mars. That money immediately stops being available for other orders.
2. Alice sends the order and reservation number directly to Mars. The number alone is not proof of funds.
3. Mars promises the matched seller's shares and asks Earth for the exact payment. Until Earth replies, the match is provisional.
4. Earth checks the order, price, destination, deadline and reservation. It consumes the reservation once, records the cash debit and sends PAYMENT.
5. Mars imports the payment, credits the seller and debits the promised shares into a delivery to Alice, in one local atomic operation. It sends DELIVERY to Earth.
6. Earth imports the shares once. Alice can now use them locally. Earth sends RECEIVED so Mars can close its recovery record.

A debit/export is a durable ledger transfer, not an unbacked promise that money will be found later. While its message is in flight, the value belongs to a named, funded transfer and cannot also be spent at its source.

## Why the four-stage cycle disappeared

The old general protocol coordinated multiple custody and clearing authorities. Prepared, committed, applied and released messages made each participant wait for distributed evidence. The new baseline restricts the problem so several of those actions can be one local ledger transaction.

| Old requirement | Current replacement |
|---|---|
| Separate preparation votes from all custody authorities | Buyer reservation plus seller inventory already at its market |
| Distributed commit certificate | Earth's irrevocable payment record for the exact promised trade |
| Separate application reports | Mars imports cash and exports shares atomically |
| Global release barrier | Each destination credits only against an existing, unique source debit |
| Separate clearinghouse coordinator | The asset's exchange handles the trade |

The economic effects are not simultaneous across planets. The seller can spend before Alice receives her shares. This is safe under the stated honest-operator assumption because the shares have already been debited into Alice's funded delivery. A lost delivery causes delay, not permission to sell those shares again.

Three business messages carry the remote trade through delivery: PAY_REQUEST, PAYMENT and DELIVERY. RECEIVED remains a fourth message for definite completion knowledge and bounded record cleanup. It is not an additional permission to let Alice spend. Local trades need only a local atomic ledger operation.

## The backing problem is addressed explicitly

Every reservation binds the owner, order ID, destination market, asset, quantity, price limit and expiry. Its entire budget is removed from available cash immediately. A valid payment consumes that reservation permanently, even if price improvement leaves some money to release.

With $150,000, Alice cannot reserve $100,000 twice. She also cannot reuse one $100,000 reservation for two different orders. A repeated identical request returns the recorded result; a conflicting request is rejected. Independent home checks remain necessary even when the market has its own duplicate detection.

Baseline orders are all-or-none against one counterparty. Smaller trades use separately funded reservations. Partial fills and amendments would require residual-budget accounting and additional race handling, so they are extensions rather than hidden complexity.

## Cancellation and outages

Earth can cancel an unpaid reservation locally: it releases the money and permanently refuses payment against it. If payment happened first, cancellation cannot refund it. Mars must keep promised shares until Earth returns either the payment or a definitive NO_PAYMENT. A timeout alone cannot tell Mars which occurred.

Packet expiry, lost receipts and session resets never erase a financial obligation. Recovery reuses the financial ID while paying for any new application messages and session setup. Long outages can leave funds pending; the system does not promise completion during an unreachable period.

Checking reservations only after a provisional match introduces an availability cost: a dishonest client can supply an invalid number and temporarily tie up inventory. One outstanding provisional match per principal, eight per market and admission backpressure limit this exposure. Prior funding verification is an optional alternative with extra traffic; the baseline does not pretend this tradeoff disappears.

## What the counts mean

These are executed **no-loss, cold-session, unbatched** examples, using actual moving-receiver geometry. Completion means both parties can use their results at home. Network loss and outages can increase time and transmissions.

| Example | Old physical transmissions | New physical transmissions | Old backbone quota originations | New quota originations | Old completion | New completion |
|---|---:|---:|---:|---:|---:|---:|
| Earth–Mars | 69 | 45 | 8 | 5 | 4.525 h | 3.067 h |
| Earth–Ceres | 149 | 45 | 17 | 5 | 4.994 h | 3.165 h |

The 45 transmissions break down as:

- One direct client order.
- Twelve physical transmissions for one cold, two-link session handshake, including hop receipts.
- Four application messages × eight physical transmissions each: two forward data hops, their two hop receipts, two reverse data-acknowledgment hops and their two hop receipts.

Only the initial SYN and four application messages consume backbone origination quota: five, split three at the market and two at the buyer's home. Automatic transport controls and receipts still consume link capacity and count as transmissions, but are exempt from that quota. The client's direct order uses its separate direct quota. A warm session structurally removes twelve handshake transmissions and one origination; that is a derived count, not another executed timing result.

## The later-price product also became simpler

The capped futures contract now holds both parties' maximum possible losses in customer escrow at Mars before opening. Funding and payout transfers are explicit and counted. This removes remote collateral-control coordination, at the cost of moving and locking capital in advance.

The same ex-ante rule covers both rising and falling prices. Each side contributes $80,000; the total $160,000 is 32% of the $500,000 opening cash. There are no interim cash payments to accidentally count again at maturity. The contract lasts 300 hours from its actual opening, and terminal allocations are transferred back home. Price observations come from the named local principal through counted local access.

## Suggested reading order

1. DESIGN sections 1–3: architecture, requirements and market location.
2. Sections 4–7: exact reservation terms, settlement states, cancellation and recovery. Read the failure table alongside the purchase sequence above.
3. Section 8: complete opening accounts, derivative funding, payoff and binding-capital example.
4. Sections 9–10: packet accounting and the evidence actually produced. The `v2_*_events.csv` and `v2_*_balances.csv` files give chronological examples.
5. Sections 11–13 and IMPLEMENTATION: the experiments and acceptance checks still needed for the paper.

The current evidence includes 27 financial tests, a bounded 19-state/190-transition exploration and four conditional packet traces. It does not yet include the complete stochastic transport simulator, full derivative packet execution or all stress scenarios. Those remain Milestone 2 work, explicitly identified rather than presented as completed evidence.
