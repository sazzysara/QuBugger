"""
Vercel Serverless Function entry point for QuBugger API.
"""
from http.server import BaseHTTPRequestHandler
import json
import os
import sys
import urllib.parse

# Add parent directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from qubugger.core import (
        CIRCUITS, build, run, passes, check_distribution,
        mutants, mutation_score, scan, repairs, localize, SHOTS
    )
    QISKIT_AVAILABLE = True
except Exception as e:
    QISKIT_AVAILABLE = False


def parse_circuit_text(text: str, n: int):
    gates = []
    for raw_line in text.strip().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.replace(",", " ").split()
        gate = parts[0].lower()
        qubits = [int(p) for p in parts[1:]]
        if gate not in ("h", "x", "z", "cx", "cz"):
            raise ValueError(f"Unknown gate '{gate}' in line: '{raw_line}'")
        for q in qubits:
            if q < 0 or q >= n:
                raise ValueError(f"Invalid qubit q{q} for {n}-qubit circuit in line: '{raw_line}'")
        if gate in ("cx", "cz") and len(qubits) != 2:
            raise ValueError(f"Gate '{gate}' requires 2 qubits in line: '{raw_line}'")
        if gate in ("h", "x", "z") and len(qubits) != 1:
            raise ValueError(f"Gate '{gate}' requires 1 qubit in line: '{raw_line}'")
        gates.append((gate, qubits))
    return gates


def format_gates_text(gates):
    return "\n".join(f"{g} " + " ".join(str(q) for q in qs) for g, qs in gates)


class handler(BaseHTTPRequestHandler):
    def _send_json(self, data, status=200):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path in ("/api/status", "/status"):
            self._send_json({
                "status": "online",
                "backend": "Qiskit Aer Simulator" if QISKIT_AVAILABLE else "Statevector Simulator",
                "shots": SHOTS if QISKIT_AVAILABLE else 4096,
                "circuits": list(CIRCUITS.keys()) if QISKIT_AVAILABLE else ["Bell", "GHZ-3", "Grover-2"]
            })
            return

        if path in ("/api/circuits", "/circuits"):
            if QISKIT_AVAILABLE:
                out = {
                    k: {
                        "name": k,
                        "n": v["n"],
                        "code": format_gates_text(v["gates"]),
                        "expected": v["expected"]
                    }
                    for k, v in CIRCUITS.items()
                }
            else:
                out = {
                    "Bell": {"name": "Bell", "n": 2, "code": "h 0\ncx 0 1", "expected": {"00": 0.5, "11": 0.5}},
                    "GHZ-3": {"name": "GHZ-3", "n": 3, "code": "h 0\ncx 0 1\ncx 1 2", "expected": {"000": 0.5, "111": 0.5}},
                    "Grover-2": {"name": "Grover-2", "n": 2, "code": "h 0\nh 1\ncz 0 1\nh 0\nh 1\nx 0\nx 1\ncz 0 1\nx 0\nx 1\nh 0\nh 1", "expected": {"11": 1.0}}
                }
            self._send_json(out)
            return

        self._send_json({"error": "Endpoint not found", "path": self.path}, status=404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path in ("/api/debug", "/debug"):
            content_len = int(self.headers.get("Content-Length", 0))
            post_body = self.rfile.read(content_len)
            try:
                data = json.loads(post_body.decode("utf-8"))
            except Exception as e:
                self._send_json({"error": f"Invalid JSON payload: {e}"}, status=400)
                return

            circuit_code = data.get("code", "")
            preset_key = data.get("preset", "Bell")
            n = data.get("n")

            ref_info = CIRCUITS.get(preset_key, CIRCUITS["Bell"])
            if n is None:
                n = ref_info["n"]
            expected = data.get("expected", ref_info["expected"])

            try:
                gates = parse_circuit_text(circuit_code, n)
            except Exception as e:
                self._send_json({"error": str(e), "success": False}, status=400)
                return

            # Execute Qiskit Aer simulation & algorithms
            counts_ideal = run(n, gates, noisy=False)
            pass_ideal, msg_ideal = passes(n, gates, expected, noisy=False)

            counts_noisy = run(n, gates, noisy=True)
            pass_noisy, msg_noisy = passes(n, gates, expected, noisy=True)

            static_issues = scan(n, gates)

            raw_repairs = localize(n, gates, expected)
            repair_list = [{"position": pos, "description": desc} for pos, desc in raw_repairs]

            k_mut, t_mut, mut_rows = mutation_score(ref_info["n"], ref_info["gates"], ref_info["expected"])
            mutants_summary = {
                "killed": k_mut,
                "total": t_mut,
                "score_pct": round((k_mut / t_mut) * 100, 1) if t_mut else 0,
                "details": [{"mutant": d, "killed": killed} for d, killed in mut_rows]
            }

            if pass_ideal and pass_noisy:
                diag = "Both pass: no code bug detected."
            elif not pass_ideal and not pass_noisy:
                diag = "Fails in ideal AND noisy runs → the code is buggy, not the hardware noise."
            elif pass_ideal and not pass_noisy:
                diag = "Passes ideal but fails noisy → circuit is sensitive to quantum noise, not a logic bug."
            else:
                diag = "Fails ideal but passes noisy → unusual distribution behavior; check statistical margin."

            self._send_json({
                "success": True,
                "n": n,
                "gates": gates,
                "ideal": {"counts": counts_ideal, "pass": pass_ideal, "msg": msg_ideal},
                "noisy": {"counts": counts_noisy, "pass": pass_noisy, "msg": msg_noisy},
                "diagnosis": diag,
                "static_scan": static_issues,
                "repairs": repair_list,
                "mutation": mutants_summary,
                "expected": expected
            })
            return

        self._send_json({"error": "Endpoint not found", "path": self.path}, status=404)
