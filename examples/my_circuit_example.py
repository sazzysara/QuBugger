"""Example: test your own circuit. Circuits are lists of (gate, [qubits])."""
import os, sys; sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from qubugger import passes, scan, localize

# Intended: a 3-qubit GHZ state -> only 000 and 111, 50/50
expected = {"000": 0.5, "111": 0.5}
my_circuit = [("h", [0]), ("cx", [0, 1])]          # bug: forgot cx(1, 2)

ok, msg = passes(3, my_circuit, expected)
print("PASS" if ok else "FAIL", "-", msg)
if not ok:
    print("static scan:", scan(3, my_circuit))
    print("candidate repairs:", localize(3, my_circuit, expected)[:5])
