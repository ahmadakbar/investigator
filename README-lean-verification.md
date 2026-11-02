# Lean spending verification

This additive package was developed against `investigator(20261101-040640).zip`.
The requested Mac directory was unavailable in this session. Extract this ZIP
into `/Users/akbarahmad2/work/My/harness/Investigator/investigator` to add it to
your checkout. It adds files; it does not replace the existing calculation,
CLI, dependency configuration, or lockfile. No new Python dependency is needed.

## Install and run

After downloading `investigator_lean_checker.zip`:

```bash
cd /Users/akbarahmad2/work/My/harness/Investigator/investigator
unzip -n ~/Downloads/investigator_lean_checker.zip

cd verification/spending
lake build
lake env lean Tests.lean

cd ../..
uv run pytest tests/test_verification.py
uv run python -m investigator.verification \
  data/demo/synthetic_personal_spending.csv \
  --output verified_spending.json
```

Lean is pinned to `leanprover/lean4:v4.35.0`, with no Mathlib dependency. Your
existing `elan` installation selects the pinned toolchain inside this directory.

Optional inclusive bounds:

```bash
uv run python -m investigator.verification \
  data/demo/synthetic_personal_spending.csv \
  --start-date 2026-04-01 --end-date 2026-09-30 \
  --output verified_spending.json
```

The command exits with status 2 on rejection, timeout, or a missing checker.
It writes a result only after successful verification. The existing
`investigator.cli analyze` command remains available and does not invoke Lean;
use this new command or wrapper when you require the verified result.

For an installed wheel or an alternate checkout location, set
`INVESTIGATOR_SPENDING_CHECKER` to the absolute binary path, or supply
`--checker /absolute/path/to/spending_checker`. The default locates the binary
under this project's `verification/spending/.lake/build/bin` directory.

## Python integration

```python
from investigator.transaction_deck import load_transactions
from investigator.verification import summarize_spending_verified

with load_transactions("data/demo/synthetic_personal_spending.csv") as deck:
    summary = summarize_spending_verified(deck)
```

`summarize_spending_verified` captures one immutable record snapshot, calls the
existing `summarize_spending` function, and sends the same snapshot, query, and
claimed result to Lean. It returns the original `SpendingSummary` only if the
checker accepts. Rejection raises `VerificationError`; no fallback releases an
unchecked result. The narrow cast in the wrapper adapts the existing
`TransactionDeck` annotation to its actual consumed interface: a record sequence
with a `digest`. No calculation is reimplemented in that adapter.

To check an existing currency-only result, call
`verify_spending_summary(deck, summary, start_date=..., end_date=...)`. Supply
the original requested bounds independently of the claimed result. This API
checks against the records observed when it is called; use the combined
wrapper to guarantee a shared snapshot for calculation and verification.

## Specification and proof

`verification/spending/SpendingSpec.lean` defines:

1. Keep only records reported as `ok` by the input adapter.
2. Keep the first valid occurrence of each exact parsed raw row. Equality uses
   all CSV field names and values, matching the existing Python deduplication.
3. Apply inclusive date bounds. With no bounds, undated records are eligible;
   with either bound, undated records are excluded.
4. Select expenses and refunds; income and transfers do not contribute.
5. For each currency independently, gross is the negated sum of signed expense
   amounts, refunds is the sum of refund amounts, and net is gross minus refunds.
6. Preserve contributing source IDs in input order and count expenses/refunds.

The adapter chooses an exact common power-of-ten unit for each currency. It
extracts `Decimal` coefficients and exponents without doing decimal arithmetic,
then sends integers to Lean. It supports integer, two-decimal, three-decimal,
and other finite decimal amounts without silently rounding them to cents.
If Python's decimal context rounded a calculation, the independent integer
calculation can reject the resulting discrepancy.

The central theorem is:

```lean
check datasetId records query claim = true →
  CorrectSummary datasetId records query claim
```

`CorrectSummary` means equality with the explicitly defined `summarizeSpec`.
It covers gross/refund/net totals, currency keys, presence of zero-valued
gross/refund entries, expense/refund counts, ordered contributing IDs, dataset
identity, and date-bound metadata. `request_check_sound` connects this theorem
to the wire handler's acceptance condition. Other theorems establish
completeness, agreement between accepted reports, and the selected source IDs.

## Exact boundary

This is verification of each accepted currency summary relative to the supplied
normalized records and specification. It is not a universal proof about every
execution of the Python interpreter or every field in `SpendingSummary`.

The following remain trusted or outside the first proof:

- CSV decoding and schema validation, including reported `ok`/`invalid`/`error`
  outcomes and their parsed transaction fields.
- The adapter's exact decimal conversion, canonical row representation, ordinal
  date conversion, dataset hash, and JSON transport.
- The Lean JSON decoder, compiler, native runtime, and local executable used to
  run the proved checker.
- The `excluded_record` list and its messages/reasons, profile/quality reports,
  category/month groupings, agent wording, and facts about a bank account.

A checker accepting a result guarantees the fields listed above; the original
summary also contains exclusion details, which have not acquired a proof merely
because they travel in the same Python object. The wrapper raises if asked to
verify a category/month grouping through this currency-only protocol.

## Files

- `src/investigator/verification.py`: Python adapter, checked wrapper, and CLI.
- `verification/spending/SpendingSpec.lean`: executable reference and proofs.
- `verification/spending/Main.lean`: one-request JSON stdin/stdout executable.
- `verification/spending/Tests.lean`: kernel-checked examples and axiom audit.
- `tests/test_verification.py`: adapter/failure tests and real native integration
  tests, including deliberately wrong claims.

The native integration tests skip when the binary has not been built. Build it
before using the test result as evidence of the Python-to-Lean connection.
