"""QuBugger prototype: statistical testing, mutation testing and fault localization for quantum circuits."""
import numpy as np
from scipy.stats import chisquare
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator
from qiskit_aer.noise import NoiseModel, depolarizing_error

SHOTS = 4096
SEED = 7

# A circuit is a list of gates: (name, [qubits]) so it can be mutated easily
def build(n, gates):
    qc = QuantumCircuit(n, n)
    for name, qs in gates:
        getattr(qc, name)(*qs)
    qc.measure(range(n), range(n))
    return qc

def noise_model(p1=0.002, p2=0.01):
    nm = NoiseModel()
    nm.add_all_qubit_quantum_error(depolarizing_error(p1, 1), ["h", "x", "z"])
    nm.add_all_qubit_quantum_error(depolarizing_error(p2, 2), ["cx", "cz"])
    return nm

def run(n, gates, noisy=False):
    sim = AerSimulator(noise_model=noise_model()) if noisy else AerSimulator()
    qc = build(n, gates)
    res = sim.run(qc, shots=SHOTS, seed_simulator=SEED).result().get_counts()
    return {k.replace(" ", ""): v for k, v in res.items()}

# ---- Module 1: statistical assertion tester ----
def check_distribution(counts, expected, alpha=0.01, leak_tol=0.0):
    """expected: {bitstring: prob}. Pass if (a) probability mass outside the expected
    outcomes is <= leak_tol and (b) a chi-square test cannot reject the expected split."""
    total = sum(counts.values())
    outside = sum(v for k, v in counts.items() if k not in expected) / total
    if outside > leak_tol:
        return False, f"{outside:.1%} of shots landed on outcomes that should never occur"
    if len(expected) == 1:
        return True, "all shots on the single expected outcome"
    obs = np.array([counts.get(k, 0) for k in expected], dtype=float)
    exp = np.array([expected[k] for k in expected]) * obs.sum()
    p = chisquare(obs, exp).pvalue
    return (p >= alpha), f"chi-square p={p:.3f}"

# ---- Reference circuits and their assertions ----
CIRCUITS = {
    "Bell": dict(n=2, gates=[("h", [0]), ("cx", [0, 1])], expected={"00": .5, "11": .5}),
    "GHZ-3": dict(n=3, gates=[("h", [0]), ("cx", [0, 1]), ("cx", [1, 2])], expected={"000": .5, "111": .5}),
    "Grover-2": dict(n=2, gates=[("h", [0]), ("h", [1]), ("cz", [0, 1]), ("h", [0]), ("h", [1]),
                                 ("z", [0]), ("z", [1]), ("cz", [0, 1]), ("h", [0]), ("h", [1])],
                     expected={"11": 1.0}),
}

def passes(n, gates, expected, noisy=False):
    leak = 0.05 if noisy else 0.0
    ok, msg = check_distribution(run(n, gates, noisy), expected, leak_tol=leak)
    return ok, msg

# ---- Module 2: mutation testing ----
def mutants(gates):
    out = []
    for i, (name, qs) in enumerate(gates):
        out.append((f"delete {name}{qs} at position {i}", gates[:i] + gates[i + 1:]))
        if name in ("cx",):
            out.append((f"swap control/target of cx{qs} at position {i}", gates[:i] + [("cx", qs[::-1])] + gates[i + 1:]))
        if name == "h":
            out.append((f"replace h{qs} with x at position {i}", gates[:i] + [("x", qs)] + gates[i + 1:]))
    return out

def mutation_score(n, gates, expected):
    killed, rows = 0, []
    for desc, m in mutants(gates):
        ok, _ = passes(n, m, expected)
        rows.append((desc, not ok))
        killed += (not ok)
    return killed, len(rows), rows

# ---- Module 3: static bug-pattern scan ----
def scan(n, gates):
    issues = []
    entangled = {q for name, qs in gates if len(qs) == 2 for q in qs}
    if n > 1 and len(entangled) == 0:
        issues.append("No two-qubit gate found: circuit cannot create entanglement")
    used = {q for _, qs in gates for q in qs}
    for q in range(n):
        if q not in used:
            issues.append(f"Qubit {q} is never used")
    return issues

# ---- Module 4: fault localization via single-edit repair search ----
def repairs(n, gates):
    cand = []
    one = sorted({g for g, qs in gates if len(qs) == 1} | {"h"})
    two = sorted({g for g, qs in gates if len(qs) == 2} | {"cx"})
    for i in range(len(gates) + 1):
        for g in one:
            for q in range(n):
                cand.append((i, f"insert {g} on q{q}", gates[:i] + [(g, [q])] + gates[i:]))
        for g in two:
            for a in range(n):
                for b in range(n):
                    if a != b:
                        cand.append((i, f"insert {g}({a},{b})", gates[:i] + [(g, [a, b])] + gates[i:]))
    for i in range(len(gates)):
        cand.append((i, f"delete gate {gates[i][0]}{gates[i][1]}", gates[:i] + gates[i + 1:]))
    return cand

def localize(n, gates, expected):
    hits = []
    for pos, desc, g in repairs(n, gates):
        if passes(n, g, expected)[0]:
            hits.append((pos, desc))
    return hits
