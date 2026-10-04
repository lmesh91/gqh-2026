# Milestone 1: prefunded trading accounts at planetary exchanges

**Design version 3.0 — current rulebook.** This replaces version 2's per-order home reservations and PAY_REQUEST/PAYMENT trade protocol. The Participant Brief and frozen `info/data.zip` remain the governing sources. Original v1 and v2 documents and evidence are historical; see `archive/` and `results/README.md`.

This is the detailed Milestone 1 specification, not the 12-page submission. `SIMPLIFICATION.md` is the reading guide; `IMPLEMENTATION.md` is the version-3 handoff to the agent doing Milestones 2–3. Existing downstream work must explicitly migrate its application rules before being described as v3 evidence. No Milestone 2–3 files are changed by this revision.

## 1. Recommended system

Each of the nine exchanges runs local accounts and the markets, registry and settlement for its assets. There are no separate clearinghouse institutions. A client has one registered home and can hold customer trading accounts at any of the nine exchanges without acquiring extra principal identities or opening wealth. Nine institutions stay within the twelve-institution limit.

**Clients fund an exchange account once and trade against its local available balances.** A transfer from Earth to Mars gives Mars exclusive spending authority over that amount. Mars can accept multiple orders, reserve money and inventory, perform partial fills, cancel remaining quantities and reinvest proceeds without contacting Earth for every fill. Cash remains customer property; the exchange's own opening capital stays zero.

The ordinary flow is:

1. Alice directs Earth to transfer cash to her registered Mars trading account. Earth durably debits her available cash and exports it through the backbone.
2. Mars imports that unique transfer once and credits her available trading balance. It sends a receipt to Earth.
3. Alice sends trading instructions to Mars by direct service. Mars checks only its authoritative local balances and order state.
4. Each fill atomically debits the buyer's reserved cash and seller's reserved shares, credits seller cash and buyer shares, and updates both orders.
5. Alice may trade again using her Mars balances. To use shares or remaining cash on Earth, she directs Mars to withdraw them. Mars debits them into a funded export; Earth imports once and acknowledges.

A local client uses one-second local access instead of the remote direct channel. Purely local matching is an atomic ledger operation, not a backbone conversation. The backbone is used when spending authority or shared registry state must cross exchanges, not when Mars reallocates its own authoritative balances.

### Accounting interpretation

The financial baseline is **prefunding by transfer of custody/spending authority**, not a revocable allowance or an unsecured credit line. If an interface calls it “$10,000 locked on Earth for Mars,” that Earth entry is a non-spendable memorandum of delegation, not a second customer cash asset. The authoritative $10,000 is in transit before import and on Mars afterward. Earth cannot infer Alice's remaining Mars balance from her original deposit: she may have spent it, earned more, or encumbered it in a contract.

A seller credited on Mars can spend or withdraw the proceeds regardless of who originally funded them. We do not tag those proceeds as money still owned by the original depositor, and do not require return to that depositor's Earth account. This is essential for a functioning trading balance rather than a per-order authorization under another name.

### Authority and trust

| State | Sole financial writer |
|---|---|
| Available balances, local order holds and local contract escrow | Exchange holding those balances |
| Order book and atomic execution record | Asset's market exchange |
| Source debit/export and immutable transfer terms | Source exchange |
| Destination import and resulting local spendability | Named destination exchange |
| Master share registry and aggregate delegated custody | Asset's registry exchange, colocated with its market |
| Beneficial balances within a delegated share allocation | Exchange holding that allocation |
| Contract position, fixing and allocation | Contract's host exchange |

Brief Section 3, page 7 assumes operators follow the rules but may crash, reset or lose connectivity. Malicious/colluding operators are an optional extension. The baseline handles dishonest clients, overspending, replay, reordering and outages. It does not protect a customer against a custodian fabricating ledger records. Prefunding makes the exposure to that custodian more concentrated; an independent verifier is an optional different trust design, not an uncounted safety assumption.

## 2. Requirements and invariants

### Source hierarchy and physical model

The brief's Section 2 fixed-parameter tables govern in case of disagreement with other brief text. The archive's orbital elements and network model govern baseline geometry. The architecture sketch and exported daily positions are design/reference inputs. No live ephemeris replaces the frozen model.

The archive contains twelve files: the orbital and network JSON, README, and nine Horizons responses. It does not contain the reference propagator mentioned in the brief. Our own implementation follows the stated equations and printed epoch checks. Six sampled dates in the separately exported CSV agree with that implementation to within 5.39×10⁻⁹ AU, but its provenance is not independently established; it is not used for sub-day flight calculations.

| Brief requirement | Current implementation/design consequence |
|---|---|
| Epoch 2026-09-22 00:00:00 TDB; 2126 is fictional label | Model time is elapsed seconds from the physical epoch; no initial 100-year shift |
| Fixed Kepler ellipses; Sun-centered 3D J2000 ecliptic AU | Use supplied mean motion and elements; negative time uses backward propagation |
| Relays at √8 AU, phases 45°/135°, prograde circles | Supplied relay parameters, not movable or additional infrastructure |
| Light time 8.317 min/AU; moving receiver; 1 ms tolerance | Solve arrival iteratively, reverse paths at their actual later emission time |
| Solar exclusion 0.10 AU | Check closest point of sender-at-emission/receiver-at-arrival segment |
| Nineteen bidirectional backbone links | Gateway–A, gateway–B, A–B only; no direct gateway backbone edge |
| Simple pinned routes, at most three links | Enumerate A, B, A→B, B→A; replacing a session requires a new handshake |
| 1 s serialization each launch; 1 s relay processing | Separate enqueue, readiness, emission, arrival, next-hop readiness |
| Client local access 1 s, lossless; direct has access at both ends | No local-access charge on backbone; same-site client instruction is local, not a direct packet |
| Independent launch loss: backbone 1−e^(−0.02d), direct 1−e^(−0.08d) | Apply to actual photon distance for every launch, including receipt/ACK directions |
| Packet 1024 bytes, header 64, payload 960, fixed-width/uncompressed | Bounded records and explicit packet counts; no hidden compression or unlimited certificates |
| Global backbone quota 600 originations per rolling 24 h | Static institution sub-budgets enforce it without a synchronized global counter |
| Direct 12 per principal per rolling 24 h, launches ≥60 s apart | Client copies, replies and institution direct traffic each use the sender's own allowance |
| SYN, initial application/control packets, resubmissions charged | Automatic retries, transport ACKs and hop receipts exempt from origination quota, not communication totals |
| Directed FIFO 1 packet/s, queue 10,000, newest dropped | Enforce serialization and bounded application backlogs; transport congestion can delay progress |
| Simultaneous arrivals: sender node ID then packet creation sequence | Authoritative sequencing follows the brief; client timestamps do not grant priority |
| Hop timer 2×flight+60 min, at most four launches | Receipt loss is different from data loss; receipts have no receipts of their own |
| Handshake SYN/SYN-ACK/ACK, receiver gates data on final ACK | No financial action merely because a SYN or transport ACK arrived |
| Endpoint timer 2T0+24 h, at most four attempts | T0 includes moving flights/serialization/relay processing, excludes queues/closure waits |
| Endpoint retry gets new packet ID, keeps byte sequence and original lifetime | Counts when enqueued; replaces older unlaunched copy; may overlap hop retries |
| Window 64 unacknowledged data packets; application delivery in order | Stricter application window of 16 used by policy; full simulator must enforce transport window too |
| Session idle expiry 7 days, IDs never reused | New handshake after expiry/reset; no exemption for recovery sessions |
| Packet lifetime 30 days; packet duplicate retention lifetime plus 30 days after last receipt | Transport expiry never cancels paid transactions or unresolved delivery obligations |
| B–Neptune [2,26), B–Ceres [240,264), once, both directions | Prevent launches whose flight interval overlaps maintenance, even before the window starts |
| Isolation 72 h, forced loss 6 h, or endpoint reset; incident unannounced | Harness applies at emission; actors cannot route using advance knowledge of hidden incident |
| Endpoint reset preserves financial records and packet-ID records | Durable application outbox rebuilds work through new sessions; old-session packets ignored |
| All shared financial-state changes use backbone | Client-carried funding references cannot credit a remote account; official transfers require backbone coordination |
| Opening ≤$500k, ≤5000 shares, 4–10 accounts at ≥3 settlements; institutions zero | Six-account book in Section 8; no hidden reserves or pre-epoch finance |
| ≥240 h obligation; two products; separate rising/falling ≥20% paths | Equity plus 300-hour capped futures, fixed rule in both directions |
| ≥25% cash encumbered; real constraint must bind | $160k futures escrow =32%; oversized position rejected for insufficient cash |
| Local spendability and matching debits define completion | Host execution, contract discharge, transfer-backed claim, home spendability and client knowledge are reported separately |
| All nine settlements access a later-price product | Funded access to the Mars contract through actual escrow transfers; no permanent exclusion |
| Indefinite market, finite accepted demand/storage/IDs | No window resets financial state; explicit caps, backpressure and engineering lifetime |
| S1–S3, E1–E5; ≥200 Julian years and shifted epochs | Retained geometry and bounded v3 account checks; v2 packet traces historical; full v3 scenario evidence still Milestone 2 |
| Paper 12 pages, appendix 12 pages, ≥10 pt, margins ≥1 inch | This research report is not the final submission; source assistance rules and clarifications still apply |

### Safety invariants

1. For every asset, opening supply equals all authoritative available balances, order holds, contract escrow and **unique exports not yet imported**. Memorandum backing, transfer claims and master-registry representations are not added again.
2. Each unit has exactly one spending authority. Export removes source availability before any destination import; a duplicate import never creates another credit.
3. At each host, total new holds and withdrawals cannot exceed available funds. Order holds and contract escrow are disjoint from available balances and from each other.
4. Each fill updates cash, shares, remaining quantities and execution deduplication in one atomic durable transaction. Both asset debits exist before either credit becomes spendable at that host.
5. Buy-order holds equal remaining quantity times limit price. Sell-order holds equal remaining quantity. A partial fill reduces the applicable holds exactly once; cancellation releases only the remainder.
6. Withdrawal consumes available funds atomically at the host. No home-side timeout, account closure request, funding expiry or client-carried proof can refund an export.
7. Packet/session expiry and resets do not erase balances, order holds, exports, import records or contract obligations. Duplicate identifiers have immutable meaning.
8. Cross-settlement completion requires actual home imports of the intended results, including remote seller proceeds. A trading-account fill alone is not reported as completed delivery home.
9. Customer account creation never creates capital, an institution identity or a fresh direct quota. Financial roles do not imply an unfunded guarantee.

## 3. Market location, account access and custody

Ares Habitat remains on Mars, Belt Works on Ceres, Terra Fabrication on Earth, and the capped futures host is Mars. Keeping the market with its registry and initial seller inventory avoids unnecessary asset repositioning. Earth–Ceres trading involves Earth and Ceres; Mars is not a mandatory intermediary.

Putting all markets on Mars/Neptune is feasible, but initial seller inventory and buyer cash must actually be transferred there. Remote proceeds and acquired inventory must be withdrawn to satisfy home completion. Prefunding can amortize those transfers over many trades, so the old two-clearer placement screen and v2 single-trade location counts are not an optimization result for this design. Compare matched workloads, including opening transfers, residual balance return and capital time away from home.

### Account registration and provenance

Each of the six scenario principals has a stable identifier and declared home; all nine exchanges know their eligibility, identity and permissible asset/account schema as configuration. Here “trading account” means a custodial subledger of one of the six fixed named scenario accounts, not a seventh (or fifty-fourth) independent scenario account. Its owner, registered home and direct quota remain unchanged. All six named accounts and their hour-0 assets are listed in Section 8; every remote custody subledger starts at zero and receives assets only by actual transfer. Account generation and requests are durable and versioned. Dynamic principal enrollment is outside the fixed-account scored runs. Any operational account-registration update requires counted authenticated communications and cannot create extra identities or quota inside a run. No funds or positions move before hour 0. Any permitted transport setup at negative time is explicitly counted.

Cash is a single conserved NeoDollar asset. Account balances are custodied customer assets, not exchange equity or freshly issued IOUs. Trading changes beneficial ownership locally without a remote funding-source approval.

The registry keeps aggregate custody by exchange, while each custodian keeps beneficial balances. A registry entry is a control record, not an additional copy of the shares. A remote holder wanting to sell shares in their listed market transfers the shares back into its market account first. Core equity withdrawals are from the registry/market to the customer's home; returns go home→registry. Arbitrary custodian→custodian share transfers use two explicit legs through the registry, avoiding a hidden third-party registry-update protocol. Registry/custodian aggregate checks account for pending exports, imports and receipt lag.

### Services and completion

All nine settlements may fund a trading account and access the Mars later-price product. Local free balances remain usable during gateway isolation. The brief's 72-hour gateway isolation fails **both backbone and direct launches** to or from that settlement; local access still works and already-emitted packets are unaffected. Existing resting orders and local instructions can therefore be processed at a funded host, but remote clients cannot assume they can send fresh orders or cancellations through the incident. A mere backbone link closure is distinct and need not block an otherwise feasible direct path.

| Operation | Host outcome | When it satisfies home delivery |
|---|---|---|
| Buy stock and retain it | Cash/stock exchange final locally at fill | Only after the acquired stock is withdrawn/imported at buyer home |
| Sell stock and retain proceeds | Seller cash final locally at fill | Only after remote seller proceeds reach seller home |
| Return unused cash | Source account debited/exported | Home imports once |
| Capped futures | Escrow and final allocation at host | Home imports each party's terminal payout |
| Local trade with both homes at host | Atomic local fill | At that fill; knowledge may follow notification |

Retention is an explicit client choice, not permission to mark a remote trade complete. In S1 baseline buy instructions select automatic home withdrawal of each fill's stock. Sellers select automatic home withdrawal of proceeds if their home differs from the market. Repeated-trading comparison runs may instead select retention and a final sweep; the delayed home-completion times remain visible.

## 4. Funding and withdrawals

### Transfer protocol

`TRANSFER(id, source, destination, principal, destination_generation, asset, amount, purpose, source_record)` is immutable and authenticated by the source institution. The baseline transfers assets between accounts of the same principal; locally executed trades handle changes of beneficial owner. The reference model supports the same-owner restriction.

1. Source validates registration, amount, integer bounds and available balance. It atomically debits that balance, records an export and its durable outbox entry.
2. Destination validates the authenticated source, destination, terms, generation and unique export ID. It atomically imports once, credits the customer's available balance (or restricted return balance for a closed generation), records the digest and queues RECEIVED.
3. Source records RECEIVED as delivery knowledge. It never re-credits the original source balance in response to a missing receipt.

Each transfer is independently final at source debit and irrevocable pending delivery; it is not a distributed commit. During transit the named customer owns a funded claim. Returning that value requires a **new transfer after import**, not deletion of the old export. Retries use the same financial ID with counted replacement network messages. Duplicate or conflicting payloads are respectively idempotent or rejected.

Top-ups are additional transfers with unique IDs. They may be used as soon as their own imports commit; the receipt need not have returned to the source. This also lets a seller withdraw freshly credited proceeds without waiting for Alice's original funding receipt.

### Withdrawal semantics

A withdrawal instruction names host account generation, client request ID, destination home, asset and exact amount, or `ALL_AVAILABLE` evaluated exactly once at host processing. It can debit only currently available funds. A cancellation is a separate local order-state change; withdrawals do not implicitly cancel orders or raid margin. New orders, fills, cancels and withdrawals serialize at the host.

Partial withdrawal does not stop trading with the remaining balance. A lost withdrawal reply may be retried with the same client ID; the host returns the same export, even if the balance has since changed. A later increase requires a new request. Delivery acknowledgments are institution-to-institution backbone messages; client-visible status is direct/local and counts separately.

The original home **cannot unlock** a delegated amount on demand or because a deadline passed. It can accept a client request to reclaim, but the actual command must reach the host through the allowed client channel; home cannot tunnel that trading/withdrawal instruction over the backbone. The host must debit and return the current unencumbered balance.

### Closing an account generation

An authenticated CLOSE processed at the host freezes admission of new orders, cancels remaining cancellable order quantities and exports released/available assets home. Existing derivative escrow stays until its contractual final allocation; those results are then automatically exported. CLOSE is idempotent, can be retried, and never authorizes home to refund a stale balance.

Status is CLOSING until local liabilities are discharged and outbound return receipts are recorded. A stale client instruction for that generation is rejected. No silent reopen: a new generation requires a recorded registration update; old instructions/exports retain their old meaning.

A late valid funding transfer to a closed/closing generation must still be imported exactly once into a restricted balance and returned to its source account (or that principal's registered home if the source generation is closed), using a fresh funded export. It cannot fund new trades, disappear or provoke a source-side refund. Known closed destinations are rejected before new export; delayed exports can still exist. Keep a compact closed-generation routing record and receive/recovery capacity for this case. Auto-returns never bounce between closed generations: a principal's registered home remains a valid receiving account for outstanding liabilities. Changing that home requires quiescent migration.

## 5. Local orders, partial fills and cancellation

### Admission

Each instruction carries principal, account generation, immutable request/order ID, asset, side, positive integer quantity, positive integer limit price, time-in-force, expiry and disposition (retain or automatic withdrawal home). No buyer-supplied deposit ID can substitute for a credited balance. Host-authenticated client identity must own the account.

If funding has not arrived, an order with insufficient available funds is **terminally rejected**; it is not silently held until funds appear. An identical retry returns that result. The client may submit a new order ID once funded. Filling order templates when deposits arrive would be a separate, explicitly authorized extension.

For a buy reserve `quantity × limit_price` in cents. For a sell reserve the specified shares already in host custody. Multiple orders are allowed only within the remaining available assets. No leverage, short inventory, cross-order double use, overdraft or borrowing against expected incoming deposits. Funds in other exchanges' accounts cannot back a host order.

### Matching

Price-time priority: best eligible price first, then host application-receipt sequence. Simultaneous arrivals obey the brief's sender node ID and packet creation sequence, with batch index as final internal tie-break. Execute at the resting order's price, within both limits. Skip self-trades; same-principal orders do not manufacture volume. An incoming order can fill successively against multiple eligible counterparties. Each partial fill is an atomic transaction with a unique execution ID.

For a fill of `q` at `p` against a buy limit `L`:

- Buyer cash hold decreases by `qL`; seller cash credit increases by `qp`; buyer available cash increases by `q(L−p)`.
- Seller share hold decreases by `q`; buyer available shares increase by `q`.
- Both remaining quantities decrease by `q`. An exhausted order becomes FILLED and cannot be revived.
- Durable fill record, order updates, balances and any selected auto-withdrawal debit/outbox commit together. Replaying the same execution cannot repeat any effect.

Standing sell inventory can be partly consumed by many buys; a buy can be partly filled by many sellers. Fees are zero. No per-fill request to the original funding exchange is necessary.

### Order lifetime and sequencing

Support GTC limit orders with an explicit maximum acceptance/expiry time, and IOC limit orders whose unmatched remainder is released immediately after matching. No indefinite abandoned hold is implied by “GTC”: every baseline order has an absolute expiry, at most 30 days after host admission. At expiry, release only the still-unfilled hold. Order expiry does not expire the account, paid executions or transfers.

CANCEL names the original order. If cancellation precedes order arrival, retain a terminal cancellation tombstone so the late order cannot open. If it follows fills, cancel only the remaining quantity. Duplicate cancel is harmless. At the same host timestamp expiry runs before new matching; among incoming instructions apply the brief's required order. No backdated client timestamp changes the host sequence.

No in-place amendment in the core protocol. Cancel and submit a new order; the new order gets new priority and must independently fit available balance. If the new instruction arrives first, the old hold still counts and it may be rejected. An atomic cancel-replace instruction can be a later counted extension, not assumed to work across messages.

Automatic withdrawals preserve usability for simple purchases, but increase traffic with partial fills. An export is created for the exact filled quantity/proceeds; unsent compatible exports may be batched at the wire level for at most 60 seconds without changing their identities. Retain-and-sweep supports cheap repeat trading and intentionally postpones home delivery.

### Worked $10,000 account

Alice funds Mars with $10,000. Two buy orders each reserve $4,000, leaving $2,000 available. A fill of the first for $1,500 at its limit leaves $6,500 held, credits its seller $1,500, and credits Alice the purchased shares. Cancelling the second releases $4,000: available $6,000, hold $2,500. She may withdraw that $6,000 or use it for another order. She cannot withdraw $10,000 or reuse the remaining $2,500 hold elsewhere. Price improvement would release the corresponding extra amount immediately at Mars.

## 6. Finality, failure and recovery

State machines: transfer `EXPORTED → IMPORTED → RECEIPT_KNOWN`; order `OPEN → PARTIAL → FILLED` or `CANCELLED/EXPIRED`, with `REJECTED` terminal; account `ACTIVE → CLOSING → CLOSED` per generation. Zero-fill OPEN can proceed directly to any terminal state. Only unfilled quantities are released. Durable journals/outboxes record atomic transitions; transport state is never the source of truth for balances.

| Event | Required outcome |
|---|---|
| Funding transfer lost | Source debit stays; retry original export; destination cannot trade absent import |
| Receipt lost after deposit | Host balance is usable; source does not refund; repeat transfer produces only another receipt |
| Client invents/reuses funding reference | No local credit, no order admission on unimported value |
| Two orders together exceed available balance | Serialized admission rejects the order that cannot be funded |
| Partial fill races cancel | Fill first consumes its quantity; cancel releases remainder. Cancel first prevents later fill |
| Withdrawal races new order | First durable operation wins access to funds; other rejects or uses remaining availability |
| Direct order lost | No order exists at host; retry same ID within direct quota |
| Direct cancel lost | Order can still fill; no claim of cancellation until host state confirms it |
| Order arrives before funding | Terminal insufficient-funds rejection; a fresh order ID is needed later |
| Unknown order cancelled first | Tombstone prevents late instruction creating an order |
| Duplicate instruction/fill/transfer | Same immutable terms return same result; changed terms under same ID reject |
| Host crash between fill and notification | All ledger effects and outbox survive; no half-fill or duplicate notification effect |
| Withdrawal transfer/receipt lost | Value remains uniquely exported/imported; replay does not refund or credit twice |
| Home isolated while host funded | Existing host orders may fill; new direct launches from that home fail; withdrawals home are funded pending |
| Host isolated | Local processing/access continue; new direct and backbone launches to/from host fail; in-flight arrivals remain possible |
| Packet/session expires | Re-establish transport and resubmit same financial object; no balance or obligation deletion |
| Close overtakes top-up | Late import is restricted and returned; no silent reactivation |
| Maturity while closing or isolated | Contract fixes and allocates locally; funded payout exports wait for home delivery |

Retries after transport reports delivery unknown, reset/expiry, or ended live retry responsibility use application backoff 24, 48, 96, then 168 hours, capped at 168 hours and postponed for known closure/quota. New application attempts and new SYNs consume quota. Responses to a newly received duplicate are charged application originations too. Recovery favors delivering existing obligations over accepting new work. No unconditional completion deadline is promised under loss/unreachability.

## 7. Quotas, demand, storage and continued operation

Each exchange has 66 backbone originations per rolling 24 hours (44 routine, 22 recovery), totaling 594 of 600. Six remain unused. No quota borrowing or live global counter is assumed. Funding, withdrawals, receipts, status, registry legs, new SYNs and application resubmissions all count when applicable. Local matching itself consumes none. A hard routine/recovery split can delay unused-category work; it is a conservative safety allocation, not optimal throughput.

Direct traffic remains 12 packets per principal per rolling 24 hours, at least 60 seconds between launches. Account proliferation never multiplies this allowance. Remote order/cancel/withdrawal/status requests and exchange-to-client direct replies count against their respective senders. There is no free live remote feed, fill notification or home-to-market command forwarding. Client apps may plan known geometry but cannot know a hidden incident ahead of time. One packet may contain bounded fixed-width instructions; batching does not make unlimited orders free.

Baseline finite offered workload is at most one new cross-exchange funding/withdrawal workflow per exchange per rolling day plus existing recoveries and maturities. The continuous trading benchmark admits at most four new client commands per active principal per day, within direct limits. Backpressure can admit less; no service guarantee follows from those offered rates. Concentrated routes, auto-withdrawal fills and payout bursts must be measured. Clients can exhaust local available funds well before quotas bind.

Bound local state: at most 32 live orders per principal per host, 256 per host, 1,024 active request-window slots per principal, 4,096 unresolved exports/import-recovery records per host, and 16 outstanding application packets per peer (below the transport window of 64). Reserve at least 20% of active financial-record capacity for recovery, returns and already accepted maturity work. Admit an auto-withdrawing fill only when its export record/outbox capacity is reserved; otherwise pause matching, never execute an unrecordable debit. Reserve return capacity for each admitted incoming transfer/workflow; sustained overload stops new funding, not recognition of existing liabilities.

Use registered 32-bit principal prefixes and durable 96-bit counters (16-byte qualified IDs). At one million Julian years and 10⁶ IDs/s, 3.16×10¹⁹ remains below 2⁹⁶. Unsigned 64-bit millisecond time covers roughly 584 million years. Reject before overflow; migrations are versioned, never counter wrap. Accounts/orders/exports/session IDs do not reset at simulation boundaries.

Compact only terminal records after the required financial receipts, safe closure of gaps, and network retention. Maintain closed-through floors per principal/namespace plus a bounded active window. Reject stale IDs below a floor rather than treating them as new. A financially unresolved old object prevents its unsafe compaction and eventually applies backpressure. Client outcome acknowledgment or a counted request watermark permits command-outcome compaction; packet loss does not. Packet ID retention covers original 30-day lifetime and 30 days after last receipt; session IDs are never reused. A reference implementation using unbounded dictionaries is a bounded test fixture, not implementation of this storage policy.

Price/time priorities and durable local atomicity assume host computation is available within declared capacity. No new financial endowment, credit advance, operating subsidy or free guarantee is introduced. Authority/home migration is quiescent: stop new obligations, resolve live exports/escrow, reconcile registry allocations, record/acknowledge the new epoch, then resume. Unreachable participants block migration rather than create two spending authorities.

## 8. Opening book and price-dependent contract

All scenarios start from this same book unless explicitly declaring a reset or permitted S3 relocation. Remote accounts start empty. Separate rising/falling runs do not share funds or results.

| Account | Home | NeoDollars | Opening shares and authority |
|---|---|---:|---|
| Alice | Earth | 150,000 | None |
| Bob | Mars | 50,000 | 3,000 Ares Habitat, Mars |
| Cara | Ceres | 100,000 | 1,000 Belt Works, Ceres |
| Dax | Neptune | 100,000 | None |
| Eve | Uranus | 50,000 | None |
| Fin | Earth | 50,000 | 1,000 Terra Fabrication, Earth |
| **Total** | **Five settlements** | **500,000** | **5,000 shares** |

### Equity scenarios

Alice funds her Mars account with $100,000 from her $150,000 Earth cash, buys 1,000 Ares shares at $100, and selects automatic withdrawal of those shares home. Bob's initial stock and home are Mars, so his proceeds are locally spendable at fill. After successful import: Alice $50k on Earth and 1,000 Ares shares; Bob $150k and 2,000 Ares shares on Mars. Other balances are unchanged. No pre-epoch prefunding is assumed.

The separate Belt scenario funds Ceres and buys 1,000 Belt shares from Cara, whose home and inventory are Ceres. After import Alice has $50k and 1,000 Belt shares on Earth; Cara has $200k and no Belt shares on Ceres. No Mars authority participates. If prefunding exceeds the purchase, unused cash stays explicitly on the host until withdrawn; returning it is extra counted work.

Repeat-trading runs start from the same book, show every partial fill/cancel/reinvestment and end with a declared sweep of remaining available assets. Report volume separately from unique wealth: recycling the same cash across trades does not increase opening capital or demonstrate the required open-position scale.

### Capped futures funded from trading accounts

Host: Mars. Alice long and Cara short first fund their Mars trading balances through actual transfers. Their explicit direct/local contract instructions independently authorize escrow; funding alone does not authorize an investment.

- Q=2,000 NeoDollars per index point, strike K=100, reference notional QK=$200,000.
- Long lifetime net payoff `Q × (clip(P,60,140) − 100)`; short receives its negative.
- Each side reserves $80,000 maximum loss **from available Mars cash into contract-specific escrow**. Margin cannot also fund stock orders or withdrawals. No rehypothecation, interim cash variation, portfolio offset or share collateral.
- Each client's accepted instruction holds its own margin while awaiting the other's acceptance. Insufficient funds reject that instruction without taking a partial margin. Opening atomically consumes both accepted holds into one position. Once OPEN, no early withdrawal/cancel; before opening, instruction cancellation/expiry releases that participant's hold locally.
- Both complete instructions and holds must exist before scenario hour 168. At that deadline an unopened contract is terminally rejected and all its remaining holds release to the respective Mars available accounts. Late generic top-ups stay available there; they do not reopen a rejected instruction/contract. To send money home requires the client withdrawal/close instruction—no v2 assumption that every deposit is a contract-tagged amount automatically refunded.
- Maturity is exactly 300 hours after actual opening. Delayed funding never shortens it below 240 hours. No free OPENED backbone message is required: authoritative position and maturity live at Mars. Remote clients obtain status by counted direct requests/replies. If the paper uses an institutional replicated position record, every corresponding message must be explicit and charged.
- Bob is the named synthetic Ares Price Index source on Mars. He learns the schedule by local access and releases one signed local observation at open+60, +120, +180, +240 and +300 hours. No free remote broadcast.
- Fix at maturity+24 hours using the scheduled maturity observation received by that cutoff; if missing or invalid/conflicting, use the latest earlier valid scheduled observation received by cutoff, or 100 if none. A conflicting pair invalidates that observation. After fixing, late or contradictory observations cannot rewrite allocation. Intermediate observations are informational only. Deterministic processing at cutoff first accepts arrivals ordered by the brief's tie-break, then fixes; the rule is published ex ante.
- Both clients' baseline instructions select automatic home payout. At fixing, allocate the escrow and debit both allocations into irrevocable home exports in the same durable transaction. A retention extension may credit available Mars balances instead, but is not home payout completion.

| Time relative to opening | Rising run | Falling run |
|---|---:|---:|
| Entry | 100 | 100 |
| +60 h | 110 | 90 |
| +120 h | 120 | 80 |
| +180 h | 130 | 70 |
| +240 h | 135 | 65 |
| +300 h | 125 | 75 |

The same ex-ante margin and fallback rules govern both paths. Each reaches 35% displacement. Final net payoff is $50k to Alice in the rising run or $50k to Cara in the falling run. Gross allocations are $130k and $30k **including original margin return**. Final home cash after both imports: Alice $200k/Cara $50k rising, or Alice $100k/Cara $150k falling; total book cash stays $500k.

Exposure is $80k per side. Open-position escrow $160k equals 32% of opening cash, independently of unused prefunding. At least 300 hours of escrow gives 48,000,000 dollar-hours, plus the fixed 24-hour fixing grace gives another 3,840,000 while awaiting allocation; add actual pre-open holds, funding/payout transit and any operational delay. Notional-normalized peak capital is 0.8. Always state numerator/denominator, and distinguish order/position encumbrance from unreserved cash merely located away from home. Record both remote capital residence and legal encumbrance; do not claim unused trading cash meets the 25% open-position criterion.

Q=2,500 requires $100k per side and is the theoretical boundary before other holds. Q=2,501 requires $100,040; Cara's $100k cannot cover it, so admission is suspended/rejected. Q=4,000 needs $160k each and exceeds Alice as well. An already-funded Mars balance does not cure insufficient total wealth. Price caps are disclosed contractual basis risk, not an unfunded margin default.

Institutional allocation discharges the net contract and creates funded payout claims. Home import makes each gross allocation locally usable; receipt gives the sender knowledge. Report these times separately. Synthetic source authentication attributes an observation but does not establish economically manipulation-resistant price discovery.

### Financial-product extensions

Capped options can use maximum-payout escrow and separately funded premiums. Covered calls require exclusively reserved shares and exercise/delivery rules. Loans and bonds create claims and liabilities but not free cash; guaranteed principal/interest needs specified backing, and volatile collateral does not guarantee cash recovery. Borrowed-stock shorts need explicit borrow/return/buy-in rules; current short exposure is the bounded futures short. A new currency requires encumbered backing and a matching liability. None is counted as an implemented second product instead of the demonstrated equity/futures pair.

## 9. Transport and packet accounting

### Preserve the brief's transport exactly

Application simplification does not remove hop receipts, transport acknowledgments, route limits, timers, packet lifetime, quotas, FIFO or maintenance.

- A new session has SYN/SYN-ACK/final ACK. Initiator may send data after queuing final ACK; receiver waits for that ACK before application release.
- Hop receipt is queued on the reverse link on reception; first data copy forwards after relay processing. Duplicate data triggers another receipt but no duplicate forwarding. Hop receipts are one-shot and are not themselves receipted.
- Every launch incurs serialization and actual moving-receiver loss. R_h starts at emission, is recalculated for each of at most four launches, and covers twice flight plus 60 min. Late receipt cancels only unlaunched retries.
- Endpoint R_e starts on enqueue, including behind a closure. At most four attempts for SYN, SYN-ACK and data; final ACK has no timer of its own. Repeated SYN-ACK can trigger another final ACK. Retry gets a new network packet ID while preserving session byte position, financial ID and original packet lifetime. Older unlaunched endpoint copy is removed; endpoint/hop retries can overlap.
- T0 is sequential empty-queue route delay including serialization and relay processing; evaluate light time even for a blocked link when calculating this timer. It does not predict a delivery deadline.
- Known solar/maintenance closure waits; a flight overlapping scheduled maintenance is not launched. A hidden incident fails launches based on emission time. Already emitted packets are not retroactively lost when an incident begins.
- Sessions expire after seven days without receipt; resets kill their volatile state. Financial records/outboxes and packet-ID records survive. Dead-session arrivals are ignored. New sessions and application queries/resubmissions count against quota.
- All launch/receipt/retry totals count toward communication efficiency even when quota-exempt. Link capacity is separate from origination quota.

### Fixed-width application records

Use a 16-byte batch header and 64-byte per-record envelope; integers are fixed-width and uncompressed. Qualified IDs are 16 bytes; asset IDs 8; principal/exchange IDs 4; amounts/prices/quantities/times 8. Envelope fields: type2, flags2, body length4, request ID16, object ID16, expected version8, event sequence8, logical time8. Header: version2, count2, principal4, batch sequence8. Envelope flags bind disposition; expected version binds account generation. All unused bytes are zero and checked.

| Record | Body bytes | Total with envelope | Records fitting payload after 16-byte header |
|---|---:|---:|---:|
| TRANSFER (funding, withdrawal, inventory or payout) | 112 | 176 | 5 |
| RECEIVED | 56 | 120 | 7 |
| ORDER | 64 | 128 | 7 |
| CANCEL / STATUS / CLOSE / WITHDRAW | 64 | 128 | 7 |
| TRADE_REPORT / ACCOUNT_REPORT | 96 | 160 | 5 |
| CONTRACT_INSTRUCTION | 192 | 256 | 3 |
| PRICE | 136 | 200 | 4 |

TRANSFER body: export ID16, source/destination IDs8, owner/home IDs8, asset8, amount8, destination generation8, source ledger sequence8, purpose8, source-record digest32, reserved8 =112. Financial transfer identity is source+export ID and its full immutable digest. RECEIVED: export ID16, digest32, destination ledger sequence8.

ORDER body: order ID16, owner4, asset8, quantity8, limit price8, expiry8, side1, time-in-force1, disposition1, reserved9 =64. Client authentication supplies principal; order fields must agree. Body and envelope are immutable. Control body: target ID16, asset8, amount8, destination4, operation/flags4, account generation8, client watermark8, reserved8 =64. `ALL_AVAILABLE` uses an operation flag; the determined amount/export is persisted for retries.

REPORT body: order/object ID16, state8, cumulative filled quantity8, remaining quantity8, available cash8, held cash8, available queried-asset quantity8, held queried-asset quantity8, ledger sequence8, last execution ID16 =96. It is a one-asset snapshot, not an unlimited fill history. Additional pages/reports are explicit counted packets. Client reports cannot import balances at another exchange.

CONTRACT_INSTRUCTION: contract ID16; canonical terms hash32; two principal/two home IDs16; host/oracle IDs8; collateral/index IDs16; Q/strike/lower cap/upper cap/per-side margin40; opening deadline/duration/observation interval/fixing grace32; observation count/rule version8; reserved24 =192. Both clients bind the same terms, account generations and automatic payout choice. PRICE: oracle4, index8, observation ID16, contract ID16, observation time8, price8, epoch4, sequence8, signature64 =136. The rule version fixes integer units, canonical hashing, payoff, fallback and roundoff.

Operator authentication is the brief's assumption, not an unimplemented Byzantine signature chain. Explicit price signatures are included. Full binary codec and network packetization tests remain Milestone 2 implementation work. Batch only records sharing sender/channel/destination, for at most 60 seconds, and preserve per-record authorization, order and deduplication. A lost batch is a shared event, not independent per-record success.

### Communication savings and honest comparisons

For an unlost two-link pinned route, one backbone application message creates eight physical transmissions: two forward launches plus two receipts, two reverse endpoint-ACK launches plus two receipts. A cold handshake adds twelve transmissions and one backbone origination. A transfer and financial RECEIVED therefore cost sixteen transmissions/two originations on a warm session, or twenty-eight/three if they alone establish a cold session. Receipts are charged application messages; transport ACKs/hop receipts remain exempt from origination quota but count as transmissions.

| Declared workflow | Backbone application records | Physical backbone transmissions | Backbone originations |
|---|---:|---:|---:|
| One initial funding, new two-link session | TRANSFER + RECEIVED | 28 | 3 |
| Any number of locally executed fills, retain assets | None per fill | 0 per fill | 0 per fill |
| One withdrawal using an existing session | TRANSFER + RECEIVED | 16 | 2 |
| Funding plus one automatic stock withdrawal, same session | Four records plus one handshake | 44 | 5 |

Add every client instruction and reply separately. A cold one-purchase flow can cost **45 physical transmissions** if funding instruction is local at Earth, the remote buyer sends one successful direct order after funds are credited, and stock auto-withdrawal uses the same session. That matches v2's transmission count, rather than proving a one-off reduction. Establishing client knowledge of funding, extra rejected early orders, separate withdrawal instructions, returning surplus cash, remote seller proceeds, partial-fill auto-withdrawals, loss and session expiry all add traffic. No v3 timing is inferred from v2's 3.067-hour result.

The 45 is a structural message count, not an executed v3 packet trace. A concrete open-loop benchmark can schedule Alice's order at a declared later time without a funding acknowledgment; if funding has not arrived, rejection is a real possible outcome. A guaranteed-to-know interactive flow must explicitly count its status response. The full simulator must execute either policy without omniscient scheduling.

For n fills with retained balances, shared initial funding and one final withdrawal, backbone boundary-transfer cost can be independent of n. But final cash and stock sweeps are separate financial transfer records, possibly one explicitly packed packet, and there may be several sellers/homes. Do not advertise a universal 44-packet entire trading session or zero communication per completed home-delivered trade. Fewer backbone messages principally benefit **repeated host trading and net withdrawals**. Report host matched turnover separately from home-delivered value: an intermediate stock purchase resold at Mars was not itself delivered home merely because the final net portfolio was swept. The S1 single-trade examples use automatic home delivery to avoid that ambiguity.

### Loss and probability

Every direct launch succeeds with `exp(−0.08d)` absent geometric/forced closure; backbone launches use `exp(−0.02d)` independently at actual flight distance, including ACK/receipts. Repeated client instructions, account reports, batch dependencies and admission timing determine end-to-end success. A missing early deposit can cause an otherwise delivered order to be rejected, so a direct success probability is not trading success.

Under open uncongested conditions one hop's no-confirmation probability is `1−(1−p_forward)(1−p_receipt)`; four-attempt bounds depend on the actual launch geometries and late-receipt cancellation. Historical isolated-hop probes remain useful only within those assumptions. They do not establish v3 account-funding or home-withdrawal completion probabilities.

## 10. Evidence status and examples

The v3 reference ledger and tests are in `prefunded_accounts.py` and `test_prefunded_accounts.py`; `checks_v3.py` runs them and emits `results/v3_*`. These exercise exclusive funding transfers, local holds/partial fills/cancellation, replay and withdrawals. The human-readable $10k worked example is Section 5. This is bounded financial evidence, not a full order-book/network implementation or proof of every interleaving.

The v2 no-loss traces, 27 tests, old 19-state exploration and 45-transmission Earth–Mars timing remain **historical**. They test different application rules and cannot validate v3. Shared geometry is reusable. No v3 stochastic, full derivative packet, long-horizon financial, or website evidence is claimed in Milestone 1. The separate agent's current Milestone 2 files have not been audited or migrated by this revision.

### Retained geometry and long-horizon evidence

Orbital work is unchanged by the financial redesign:

- Maximum coordinate error against rounded epoch table: 4.679×10⁻⁷ AU, below 10⁻⁵ AU.
- Supplied-period return and radius-bound checks pass. Moving-receiver residuals are tested at negative time, hour 300 and 200 years.
- Earth→Mars at emission t=0: 860.995951 s moving flight vs 860.951655 s frozen, +44.297 ms. Reverse emitted at t=0: 860.875366 s, −76.289 ms from frozen. Actual trace replies use later emission geometry.
- Maintenance check correctly excludes Neptune→B emitted at t=0 because the flight overlaps the hour-2 maintenance start.
- 200-year hourly scan: 1,753,201 epochs, all 38 directed links, moving-receiver solar clearance, no repetition of one-time maintenance.
- Refined Mercury→A open-to-blocked emission boundary: original [7,135,200, 7,138,800] s bracket to [7,138,362.320137, 7,138,362.320995] s, under 1 ms. Already emitted photons are evaluated by their own path, not retroactively erased by a later boundary.
- Chosen difficult screening epoch: hour 993,506, approximately 113.34 years. Exact Neptune→A→B→Mars forward delay 314.876465 min, reverse 314.849888 min; first-hop loss about 45.72%.

An hourly grid detects continuous closures longer than an hour but can miss shorter/grazing closures. The long-scan route screen evaluates links at a common epoch, so it is not exact sequential forwarding near boundaries. Its sampled connectivity and extrema are not proof of perpetual access. Retain **E4 Tier 2 candidate** status; Tier 3 requires exact route/window refinement for the current service graph. The known orbital model is an indefinite mathematical challenge model, not an accurate real solar-system ephemeris for eternity.

Hour-0 / hour-300 best routes to the Mars equity/contract market remain:

| Settlement | Route at both hours | Delay min at 0 / 300 | Sampled next-24h route launch availability |
|---|---|---:|---|
| Mercury | Mercury–A–Mars | 42.368 / 42.032 | 100% / 100% |
| Venus | Venus–A–Mars | 36.911 / 35.923 | 100% / 100% |
| Earth | Earth–A–Mars | 33.912 / 33.444 | 100% / 100% |
| Mars | Internal | 0 / 0 | 100% / 100% |
| Ceres | Ceres–A–Mars | 29.713 / 30.500 | 100% / 100% |
| Jupiter | Jupiter–B–Mars | 39.905 / 39.233 | 100% / 100% |
| Saturn | Saturn–A–Mars | 75.766 / 77.124 | 100% / 100% |
| Uranus | Uranus–A–Mars | 154.611 / 154.988 | 100% / 100% |
| Neptune | Neptune–A–Mars | 246.846 / 248.330 | 100% / 100% |

Availability here samples every minute and means all links of the selected route can launch at that sampled time, not session delivery probability. S3 must include the actual market, funding, inventory and payout authorities for each offered product, including reverse routes. Mars is best, Jupiter median and Neptune worst by this Mars-route ranking. The all-local Mars stock trade is an atomic local operation after both instructions arrive (analytical 1 s for simultaneous initial local instructions); v2 median/worst traces are historical comparisons and must be rerun for prefunding plus withdrawals. Client knowledge follows local notification and is distinct from local balance availability.

## 11. Scenario and evidence handoff

### S1 and repeated trading

Use separate declared resets from the complete opening book for: (1) funded Earth–Mars share purchase with automatic home stock withdrawal, initially ending hour48; (2) analogous Earth–Ceres; (3) Alice/Cara Mars futures rising; (4) falling, same rules; (5) Q=2,500 boundary and Q=2,501/4,000 rejected variants. Derivative runs initially end hour600; retain named funded owners for all unresolved account balances, margin or exports. At least one completed derivative run must actually reach $160k simultaneous open-position escrow and remain open300h; funded cash sitting unused at Mars does not substitute for that condition.

Add a repeat-trading scenario covering two concurrent orders, partial fills, price improvement, cancellation, spending proceeds and a final withdrawal. Compare v2 versus v3 only for a common supported economic workload and identical home-completion condition. Since v2 rejects partial fills, compare equivalent separately funded child orders or clearly label the capability difference. Charge all setup, local/direct controls, reports, final sweeps, retries and unused-capital residence. Never seed a free funded Mars account at hour0.

### S2 and failure coverage

Candidate: isolate Mars around futures fixing/home payouts, exposing concentration of margin at the host. Other candidates include funding import before lost receipt, cancel/withdrawal races and a reset immediately after partial fill or export. Search the allowed 72h isolation,6h loss and endpoint reset targets/start times; actors learn only through observable failures. Include the later-price product in the selected S2 run.

Run maintenance-off comparison at the same incident time. For a same-funding, same-final-home-guarantee alternative compare auto-withdrawal per fill against retain-and-final-sweep, including their different home-availability times and capital residence. Direct-copy policies are another counted sensitivity. Old prior-funding-versus-on-demand payment verification is no longer the v3 baseline comparison. Recovery means restoring a financial service, not merely reopening a link.

### E1–E5 and S3

| Evidence | Reusable/current | Needed for v3 submission |
|---|---|---|
| E1 | Frozen geometry/epoch/residual checks | Selected funding and withdrawal paths at actual emissions |
| E2 | Structural packet accounting only; v2 traffic historical | Full packet traces including funding, client status policy, partial fills and withdrawals; lossy queues/retries/resets |
| E3 | Bounded v3 account model/tests and capped-payoff arithmetic | Full named-account audit, registry reconciliation, derivative opening/fixing, asset-hours and sweeps |
| E4 | 200-year hourly link screen and refined boundary | Exact sequential windows for the current funding/trading/withdrawal service graph if claiming Tier3 |
| E5 | Shifted geometry and difficult epoch | Full v3 runs at +1,+10,+100 years and difficult epoch, both price directions, no repetition of original maintenance |

S3 must demonstrate all nine sites' ability to fund Mars and withdraw results, alongside Earth/Mars/Ceres asset markets; rank access by actual service completion, not forward funding flight alone. Relocate one existing account and assets without creating wealth. Compare same local-spendability target and report funded pending when not complete. Symmetric payoff does not imply symmetric network completion when winners/homes change.

The Milestone 3 website must expose balances by location: home available, host available, order holds, contract escrow and exported pending. Show local fill and home completion separately; every visual animation must replay the authoritative event stream. Include client quota usage, rejected orders awaiting a top-up, failed cancels and withdrawal status rather than implying instant remote control.

## 12. Deployment and limits

Two numerical real-deployment effects remain explicitly outside the common baseline:

1. NASA's Earth radius 6378.137 km and sidereal rotation 23.9345 h imply equatorial surface speed about 0.4651 km/s. A single equatorial ground station viewing a roughly equatorial distant target with zero elevation mask can have approximately **11.97 h below-horizon intervals**. The brief folds these effects into always-available one-second local access. A real system would need additional visibility support or tolerate longer waits. Exclusive backing remains safe if waits are explicit; baseline latency promises would change. [NASA Earth Fact Sheet](https://nssdc.gsfc.nasa.gov/planetary/factsheet/earthfact.html).
2. An illustrative 30 km/s radial relative speed at a 32 GHz carrier gives Doppler shift about **3.20 MHz** using fv/c. The speed is an assumption of Earth's orbital-velocity scale, not a calculated Earth–Mars radial velocity. ESA documents 32 GHz use and Doppler tracking. Real modems must track that shift or incur additional loss; the conservative financial invariants tolerate loss/delay, not arbitrary undetected corruption or forged identities. [NASA Earth Fact Sheet](https://nssdc.gsfc.nasa.gov/planetary/factsheet/earthfact.html), [ESA Cebreros](https://www.esa.int/Enabling_Support/Operations/ESA_Ground_Stations/Cebreros_-_DSA_2), [ESA Delta-DOR](https://www.esa.int/Enabling_Support/Operations/Keeping_track_of_spacecraft_with_Delta-DOR).

No unlisted network links, local satellite orbits, free broadcasting, legal enforcement, credit advance or future endowment is introduced. No guarantee depends on all-time uninterrupted connectivity or free operator financial resources.

The external settlement analogy is delivery-versus-payment: recipients should not obtain spendable results without corresponding recorded asset debits. The prefunded model implements this through atomic host trades and uniquely backed transfers between exchanges. [CPMI–IOSCO PFMI overview](https://www.bis.org/committees/cpmi/pfmi/overview). Durable commitments can still block when parties are unreachable; eliminating redundant rounds does not create a nonblocking distributed system. [Gray and Lamport, Consensus on Transaction Commit](https://arxiv.org/abs/cs/0408036).

## 13. Decisions and implementation boundary

The baseline is now prefunded per-exchange customer accounts, local price-time matching with partial fills, exclusive order holds, cancel-and-new amendment, atomic host settlement, optional retained inventory and explicit home withdrawals. Per-order home reservations and PAY_REQUEST/PAYMENT are removed from the core flow. Fully collateralized futures reserve local host funds under one ex-ante rule.

Remaining work is execution and evidence: implement the full transport and matching engine, durable outboxes/capacity/compaction, binary encoding, derivative lifecycle, stress and shifted runs, then paper and website. Existing downstream code must be reviewed against the migration checklist. This design makes no claim that historical v2 traces or newly written bounded tests establish every production behavior.
