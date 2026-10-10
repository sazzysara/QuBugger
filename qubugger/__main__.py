"""Run the full QuBugger demo:  python -m qubugger"""
from . import *
import warnings; warnings.filterwarnings("ignore")

def main():
    print("=== 1. Correct circuits (ideal vs noisy) ===")
    for name, c in CIRCUITS.items():
        ci, mi = passes(c["n"], c["gates"], c["expected"])
        cn, mn = passes(c["n"], c["gates"], c["expected"], noisy=True)
        print(f"{name:9s} ideal: {'PASS' if ci else 'FAIL'} ({mi}) | noisy: {'PASS' if cn else 'FAIL'} ({mn})")

    print("\n=== 2. Bell circuit with the CNOT removed ===")
    c = CIRCUITS["Bell"]; buggy = [("h", [0])]
    print("counts:", run(2, buggy))
    for label, noisy in (("ideal", False), ("noisy", True)):
        ok, msg = passes(2, buggy, c["expected"], noisy=noisy)
        print(f"{label}: {'PASS' if ok else 'FAIL'} - {msg}")
    print("static scan:", scan(2, buggy))
    print("candidate repairs (position, edit):", localize(2, buggy, c["expected"])[:5])

    print("\n=== 3. Mutation testing ===")
    for name, c in CIRCUITS.items():
        k, t, rows = mutation_score(c["n"], c["gates"], c["expected"])
        print(f"{name}: killed {k}/{t} mutants ({k/t:.0%})")
        for d, killed in rows:
            if not killed: print("   survived:", d)

    print("\n=== 4. Fault localization on injected bugs ===")
    tot = hit = 0
    for name, c in CIRCUITS.items():
        for desc, m in mutants(c["gates"]):
            if passes(c["n"], m, c["expected"])[0]:
                continue  # equivalent mutant, not a real bug
            pos = int(desc.split("position ")[1])
            found = any(abs(h[0] - pos) <= 1 for h in localize(c["n"], m, c["expected"]))
            tot += 1; hit += found
    print(f"Repair found within +/-1 gate of the true bug: {hit}/{tot} ({hit/tot:.0%})")

if __name__ == "__main__":
    main()
