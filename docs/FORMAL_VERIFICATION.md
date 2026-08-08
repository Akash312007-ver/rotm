# Formal Verification of ROTM's Double-Spend Detection Protocol

## What is TLA+?

TLA+ (Temporal Logic of Actions) is a formal specification language created
by Leslie Lamport for precisely describing and verifying concurrent and
distributed systems. Instead of testing a handful of scenarios (as unit
tests do), TLA+'s companion tool, **TLC**, exhaustively explores every
possible sequence of actions a system can take within specified bounds, and
checks that a stated property never breaks.

- **Code** describes *how* a system is implemented.
- **TLA+** describes *what* a system must always be true.
- **TLC** proves the "what" holds for every reachable state, or produces an
  exact counterexample if it doesn't.

## Why This Matters for ROTM

ROTM's central safety claim (`docs/PROTOCOL.md`, Section 4.2) is: *no
ledger, after any sequence of merges, ever believes it has committed more
spend for a sender than that sender's known balance.* This is a **safety
property** in a **distributed system** — exactly the class of claim that is
notoriously easy to get subtly wrong (ordering bugs, edge cases in conflict
resolution, race conditions between concurrent merges) and that unit tests
alone cannot fully confirm, because unit tests only check the specific
scenarios someone thought to write.

## What Was Modeled

`docs/ROTM.tla` models the exact logic of `sync/ledger.py`'s `submit()` and
`merge()` functions:

| Real code | Modeled as |
|---|---|
| `Wallet.create_transaction()` + `submit()` | `CreateAndSubmit` action |
| Malicious client reusing a nonce (`sync/mesh_simulator.py`'s attack sim) | `MaliciousDoubleSpend` action |
| `Ledger.merge()` | `MergeLedgers` action |
| The core `submit()` accept/reject check | `SubmitTxn` |

The model lets TLC choose, at every step, any wallet, any ledger, and any
action (honest transaction, double-spend attempt, or merge) — in any order,
interleaved arbitrarily — and checks the safety invariant after every single
step.

## What Was NOT Modeled (Intentional Scope)

| Excluded | Why |
|---|---|
| Cryptographic signatures | Assumed unforgeable — a separate, well-studied problem, not this protocol's concern |
| Network timing / real delays | TLA+ models *any possible interleaving*, which is a stronger check than modeling specific timing |
| Sybil-resistance (Section 8) | A separate protocol layer; verifying it is future work |
| LLM risk scoring | Advisory-only, doesn't affect the safety property |
| Offline cap enforcement | Wallet-local policy, orthogonal to ledger-level double-spend detection |

This is a standard and correct scoping choice: formal verification is most
useful on a small, precise core rather than an entire system at once.

## Actual Verification Result (Real, Not Simulated)

Run directly on Anthropic's sandboxed environment using the official TLA+
tools (`tla2tools.jar`, downloaded from the TLA+ GitHub releases) and OpenJDK
21:

```
java -cp tla2tools.jar tlc2.TLC -config ROTM.cfg ROTM.tla
```

**Result:**
```
Model checking completed. No error has been found.
Estimates of the probability that TLC did not check all reachable states
because two distinct states had the same fingerprint:
  calculated (optimistic):  val = 5.9E-8
  based on the actual fingerprints:  val = 1.4E-9
5992721 states generated, 187489 distinct states found, 0 states left on queue.
The depth of the complete state graph search is 9.
Finished in 31s.
```

**187,489 distinct states** were exhaustively checked — every reachable
combination of wallet actions, double-spend attempts, and ledger merges
within the model's bounds (2 wallets, 2 ledgers, nonces 0-2, amounts {2,3},
balance 5) — and **zero violations** of the balance invariant were found.

An earlier iteration of this exact model *did* catch a real bug (an
off-by-one in the model's own nonce-boundary condition, not in ROTM's actual
protocol logic) — which is itself a demonstration of the process working
correctly: TLC found the bug, we fixed the model, re-ran, and got a clean
result. This trace is preserved in the project's development history rather
than hidden, in keeping with this project's practice of reporting only
verified results.

## How to Reproduce This Yourself

1. Install Java 8+ (any recent JDK works)
2. Download `tla2tools.jar` from
   https://github.com/tlaplus/tlaplus/releases
3. Run:
   ```
   java -cp tla2tools.jar tlc2.TLC -config docs/ROTM.cfg docs/ROTM.tla
   ```
4. Expect the "No error has been found" result above, in well under a
   minute on an ordinary laptop.

## Honest Limitations of This Verification

- The model is intentionally small (2 wallets, 2 ledgers, bounded nonces
  and amounts) to make exhaustive checking fast. A larger model (more
  wallets/ledgers/nonce range) would increase confidence further but take
  proportionally longer to check — state space grows combinatorially.
- This proves the *modeled* logic is correct, not that the Python
  implementation perfectly matches the model. The model was written by
  directly translating `sync/ledger.py`'s actual accept/reject logic,
  but a manual line-by-line correspondence check (not automated
  translation) is what connects the two.
- **Liveness** (i.e., "a double-spend attempt is *eventually* detected
  given enough merges") is not proven here — only the safety property
  (something bad never becomes true) is checked. Liveness proofs require
  additional fairness assumptions and are a natural next step.

## Next Steps

1. Extend the model to include the Sybil-resistance layer (Section 8) and
   re-verify the combined system.
2. Prove a liveness property with fairness assumptions.
3. Property-based testing (e.g., Python's `hypothesis` library) using the
   same invariant, to cross-check the model against actual running code
   rather than a hand-translated logical model.

## References

- Lamport, *Specifying Systems* — the standard TLA+ reference, free PDF at
  https://lamport.azurewebsites.net/tla/book.html
- TLA+ Toolbox and tools: https://github.com/tlaplus/tlaplus
- `docs/PROTOCOL.md` Sections 2-4 — the informal protocol description this
  specification formalizes
