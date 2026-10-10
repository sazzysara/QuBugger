"""QuBugger: automated debugging and testing for quantum programs."""
from .core import (CIRCUITS, build, run, passes, check_distribution,
                   mutants, mutation_score, scan, localize)
__all__ = ["CIRCUITS", "build", "run", "passes", "check_distribution",
           "mutants", "mutation_score", "scan", "localize"]
__version__ = "0.1.0"
