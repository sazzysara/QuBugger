# QuBugger

**An automated debugging and testing framework for quantum programs.**
Built by team **InnoVentors** for Q-Hack India 2026 (Track: Quantum AI with Software).

## The problem
Quantum programs are hard to debug: measuring a qubit destroys its state, qubits cannot be copied, outputs are probabilistic, and hardware noise hides real bugs. A Bell-state circuit with one missing gate runs without errors and silently gives wrong results.

## What QuBugger does
QuBugger tests behavior from measured outputs, so no qubit inspection is needed. It runs on a simulator (Qiskit Aer), no hardware required.

| Module | What it does |
|---|---|
| Assertion testing | Checks output distributions against expected behavior (chi-square test, ideal and noisy runs) |
| Mutation testing | Injects deliberate bugs (delete gate, swap CNOT, H to X) and scores how many the tests catch |
| Bug-pattern scan | Static check, e.g. "no two-qubit gate, so no entanglement is possible" |
| Fault localization | Tries single-gate repairs; the position of a repair that makes the tests pass points at the likely bug |

## Quick start
```bash
git clone <your-repo-url> && cd qubugger
pip install -r requirements.txt
python -m qubugger                      # full demo
python examples/my_circuit_example.py
pytest -q                               # run the tests
```

## Example output (Bell circuit, CNOT removed, 4096 shots)
```
counts: {'00': 2039, '01': 2057}
ideal: FAIL - 50.2% of shots landed on outcomes that should never occur
noisy: FAIL - 49.9% of shots landed on outcomes that should never occur
static scan: ['No two-qubit gate found: circuit cannot create entanglement', 'Qubit 1 is never used']
candidate repairs: [(1, 'insert cx(0,1)')]
```

## Results so far (simulation only)
- Correct Bell, GHZ-3 and Grover-2 circuits: 3/3 pass, ideal and noisy
- Mutation testing: 26/26 injected bugs caught
- Fault localization: 24/26 (92%) found a working repair within 1 gate of the true bug

## Limitations
- Validated only on three small circuits (2-3 qubits) in simulation, with a fixed random seed
- Localization returns a short list of candidate repairs, not a single answer; the 2 misses need a two-edit repair
- Not yet tested on real hardware or real-world bug datasets
- No quantum speedup is claimed: QuBugger is classical software that tests quantum programs

## Roadmap
Cirq/OpenQASM input, more mutation operators (angles, qubit order) and assertion types, ML-based gate ranking, larger-circuit simulators, noise models from IBM backend data, IBM Quantum hardware runs, pytest plugin, benchmarks on Bugs4Q.

## Inspiration and references
- Huang and Martonosi, *Statistical Assertions for Validating Patterns and Finding Bugs in Quantum Programs*, ISCA 2019
- Mendiluze et al., *Muskit: A Mutation Analysis Tool for Quantum Software Testing*, ASE 2021
- Zhao et al., *Bugs4Q: A Benchmark of Real Bugs for Quantum Programs*, ASE 2021
- Qiskit and Qiskit Aer documentation; SciPy

This implementation is the team's own work.

## License
MIT
