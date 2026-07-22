# Developer guide

Run `python3 tests/run_all.py` before packaging. New state-changing operations must use the command and revision contracts, must not infer readiness in frontend code, and must add a regression test. New scientific models must document source, assumptions, validity domain, parameters, fidelity, tests, and affected metrics.
