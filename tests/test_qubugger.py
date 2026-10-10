import pytest
from qubugger import CIRCUITS, passes, mutants, mutation_score, scan, localize

@pytest.mark.parametrize("name", list(CIRCUITS))
def test_correct_circuits_pass_ideal_and_noisy(name):
    c = CIRCUITS[name]
    assert passes(c["n"], c["gates"], c["expected"])[0]
    assert passes(c["n"], c["gates"], c["expected"], noisy=True)[0]

def test_missing_cnot_is_detected_and_repaired():
    c = CIRCUITS["Bell"]; buggy = [("h", [0])]
    assert not passes(2, buggy, c["expected"])[0]
    assert not passes(2, buggy, c["expected"], noisy=True)[0]
    assert any("cx" in d for _, d in localize(2, buggy, c["expected"]))
    assert scan(2, buggy)

@pytest.mark.parametrize("name", list(CIRCUITS))
def test_mutation_tests_kill_all_mutants(name):
    c = CIRCUITS[name]
    killed, total, _ = mutation_score(c["n"], c["gates"], c["expected"])
    assert killed == total
