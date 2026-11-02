# Validation performed

Validated on 2026-11-01 against the latest supplied project archive,
`investigator(20261101-040640).zip`.

- Lean 4.35.0: Lake built `SpendingSpec`, `Main`, and the native checker.
- Lean `Tests.lean`: all five executable examples/proofs passed.
- Axiom audit: the checker soundness, request soundness, report agreement, and
  source-row theorems use only `propext`, `Classical.choice`, and `Quot.sound`.
  The net-identity theorem uses no axioms. No reported dependency is `sorryAx`
  or a custom/native-evaluation axiom.
- Python 3.12.14, Pydantic 2.14.1, pydantic-extra-types 2.11.1, pycountry
  26.2.16, pytest 9.2.0: **64 passed, zero skipped**, comprising the 30 existing
  project tests and 34 new verification cases. Native integration cases used
  the actual compiled Lean executable, including intentional claim corruption.
- Ruff 0.17.3: both new Python files pass the project's lint configuration.
- The source files packaged here match the copies used by these checks.

The supplied full demo CSV was processed with the new verified command:

| Checked field | Result |
| --- | --- |
| EUR net spending | 16186.74 |
| USD net spending | 87.00 |
| Expense count | 280 |
| Refund count | 1 |
| Contributing source IDs | 281 |

The original summary also reports 23 excluded records; their messages and
reasons are outside this first formal specification.

This Linux execution environment cannot discover an application's own binary
location. To run the released Lean libraries, validation used a small embedding
launcher that initializes their search path explicitly and invokes the
unchanged official elaborator/compiler and standard proof kernel. Lake and the
generated checker then ran natively. This launch adaptation is local test
infrastructure and is not part of the package or required on your Mac.

The Mac checkout was not mounted, so these files have not been installed into
that directory. Follow `README-lean-verification.md` to add and build them there.
