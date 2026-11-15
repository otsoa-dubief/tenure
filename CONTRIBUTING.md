# Contributing to Tenure

Thanks for helping. Issues, ideas and pull requests are all welcome; the issues labelled `good first issue` are a good place to start.

## Set up

Tenure needs Python 3.11 or later and has no required dependency outside the standard library.

```
git clone https://github.com/otsoa-dubief/tenure
cd tenure
python3 -m venv .venv
.venv/bin/pip install pytest cryptography fastapi httpx
.venv/bin/python -m pytest -q tests
```

`cryptography` signs passports; `fastapi` and `httpx` run the dashboard API tests. Hermes itself is not needed to run the tests.

## Ground rules

- **Local and deterministic.** Tenure makes no network call and no LLM call, and the same inputs always give the same decision. A change that breaks this will not be merged.
- **The rule is preregistered.** `tenure/rule.py`, `tenure/params.py` and the thresholds they hold are the rule of a preregistered study, fingerprinted in every passport. Changing them is a new rule version, discussed in an issue first.
- **Stricter by default.** When a case is unclear, Tenure asks. A change that lets an agent act alone where it used to ask needs a clear argument and a test.
- **Every message in every language.** User-facing text lives in `tenure/locales/` (one folder per language); add new keys to every language.
- **Docs move with the code.** If behaviour changes, update the README or `docs/` in the same pull request.

## Pull requests

- One topic per pull request, with tests that fail without the change.
- The full suite must pass on all CI jobs (Python 3.11 to 3.14, Windows, and the end-to-end check in the Hermes image).
- History is kept linear: pull requests are merged by rebase.
- Write commit messages that say what changed and why, in plain words.

## Security

Please report vulnerabilities privately, not in an issue: see [SECURITY.md](SECURITY.md).
