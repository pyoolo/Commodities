# Adding a project

The value of a container repo is consistency: a reader who understands one project should be able to navigate any other without re-learning the layout. These are the conventions that hold.

## Layout

```
projects/NN-short-name/
├── README.md            the write-up
├── <package>/           uniquely named — never "src"
│   ├── __init__.py
│   └── *.py
├── tests/
├── outputs/             generated; committed so the README renders on GitHub
└── run_analysis.py      regenerates everything in outputs/
```

Register the new project directory in `pyproject.toml` under `[tool.pytest.ini_options] pythonpath` so its package resolves during a full-suite run.

**On the package name.** Two projects both containing `src/` will shadow each other the moment `pytest` collects them together, and the failure is confusing when it happens. Use something descriptive: `fwdcurve`, `storagevalue`, `sparkspread`.

## The write-up

Structure, in this order:

1. **The question**, stated as a question in bold at the top. If you cannot phrase it as one, the project is a utility and belongs in `cqr_core`.
2. **Why it matters** — what downstream decision depends on the answer.
3. **The problem**, set up precisely, with the maths where maths is clearer than prose.
4. **The method**, including the choices that could have gone the other way and why they did not.
5. **Results**, with figures, and against a named baseline.
6. **Limitations** — mandatory, and specific. "This is a simplified model" is not a limitation; "the smoothness penalty will smear a structural break across the break" is.
7. **Reproduce** — the exact commands.

Write the limitations section honestly. A reader who finds a flaw you did not mention discounts everything else; a reader who finds you already named it trusts the rest.

## Baselines

Every result needs something to beat, and the baseline should be what a practitioner would actually do — not a strawman. Project 01 compares against a flat step unpack because that is the common desk shortcut, not against a random curve.

## Tests

The suite is the argument that the model does what the write-up claims. Aim for:

- **Exact properties tested exactly.** Where a property follows from the maths — no-arbitrage reconstitution, invariance to an irrelevant parameter, a limiting case — assert it to machine precision. Loose tolerances chosen after seeing the output test nothing.
- **Invariances.** If the write-up says a parameter should not affect the answer, test that it does not. Project 01's shape-prior level test caught a real bug this way.
- **Degenerate inputs.** Single quote, empty input, rank-deficient constraints, zero weights.
- **The baseline comparison**, so a regression that quietly makes the method worse than the naive approach fails CI.

## Data

Synthetic only. Generators live in the project package, are seeded, and expose the ground truth they generated so tests can check recovery against it. No vendor data, no scraped screens, nothing under licence.

## Style

- Comments explain the *modelling* choice. `# second differences, not first: a slope penalty would fight the seasonal trend` is useful. `# loop over products` is not.
- Docstrings state what a function is for and what could go wrong with it, not just its signature.
- `ruff check .` passes.
- Keep the numerics readable. If a closed form exists, use it and say so; if you reach for an iterative solver, say why the closed form did not survive.
