"""
QuBugger Web Server
Provides full REST API and serves the interactive frontend prototype.
"""
import http.server
import json
import os
import sys
import urllib.parse
from typing import Dict, Any, List

# Ensure package root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from qubugger.core import (
        CIRCUITS, build, run, passes, check_distribution,
        mutants, mutation_score, scan, repairs, localize, SHOTS, SEED
    )
    QISKIT_BACKEND = True
except Exception as e:
    print(f"[Warning] Failed to load Qiskit Aer backend: {e}")
    QISKIT_BACKEND = False


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
                raise ValueError(f"Invalid qubit q{q} (circuit has {n} qubits) in line: '{raw_line}'")
        if gate in ("cx", "cz") and len(qubits) != 2:
            raise ValueError(f"Gate '{gate}' requires 2 qubits in line: '{raw_line}'")
        if gate in ("h", "x", "z") and len(qubits) != 1:
            raise ValueError(f"Gate '{gate}' requires 1 qubit in line: '{raw_line}'")
        gates.append((gate, qubits))
    return gates


def format_gates_text(gates):
    return "\n".join(f"{g} " + " ".join(str(q) for q in qs) for g, qs in gates)


class QuBuggerHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        # Serve static files from static directory or repo root
        static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "static"))
        if not os.path.exists(static_dir):
            static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        super().__init__(*args, directory=static_dir, **kwargs)

    def _send_json(self, data: Dict[str, Any], status=200):
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
        if parsed.path == "/api/status":
            self._send_json({
                "status": "online",
                "backend": "Qiskit Aer Simulator" if QISKIT_BACKEND else "Fallback Statevector Simulator",
                "shots": SHOTS,
                "circuits": list(CIRCUITS.keys())
            })
            return
        elif parsed.path == "/api/circuits":
            out = {}
            for k, v in CIRCUITS.items():
                out[k] = {
                    "name": k,
                    "n": v["n"],
                    "code": format_gates_text(v["gates"]),
                    "expected": v["expected"]
                }
            self._send_json(out)
            return

        # Default static file handling
        if parsed.path == "/" or parsed.path == "/index.html":
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/debug":
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

            # Reference circuit info
            ref_info = CIRCUITS.get(preset_key, CIRCUITS["Bell"])
            if n is None:
                n = ref_info["n"]
            expected = data.get("expected", ref_info["expected"])

            try:
                gates = parse_circuit_text(circuit_code, n)
            except Exception as e:
                self._send_json({"error": str(e), "success": False}, status=400)
                return

            # Run ideal and noisy tests
            counts_ideal = run(n, gates, noisy=False)
            pass_ideal, msg_ideal = passes(n, gates, expected, noisy=False)
            
            counts_noisy = run(n, gates, noisy=True)
            pass_noisy, msg_noisy = passes(n, gates, expected, noisy=True)

            # Static scanner
            static_issues = scan(n, gates)

            # Fault localization
            raw_repairs = localize(n, gates, expected)
            repair_list = []
            for pos, desc in raw_repairs:
                repair_list.append({
                    "position": pos,
                    "description": desc
                })

            # Mutation testing on reference circuit
            k_mut, t_mut, mut_rows = mutation_score(ref_info["n"], ref_info["gates"], ref_info["expected"])
            mutants_summary = {
                "killed": k_mut,
                "total": t_mut,
                "score_pct": round((k_mut / t_mut) * 100, 1) if t_mut else 0,
                "details": [{"mutant": d, "killed": killed} for d, killed in mut_rows]
            }

            # Diagnosis message
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
                "ideal": {
                    "counts": counts_ideal,
                    "pass": pass_ideal,
                    "msg": msg_ideal
                },
                "noisy": {
                    "counts": counts_noisy,
                    "pass": pass_noisy,
                    "msg": msg_noisy
                },
                "diagnosis": diag,
                "static_scan": static_issues,
                "repairs": repair_list,
                "mutation": mutants_summary,
                "expected": expected
            })
            return

        self._send_json({"error": "Endpoint not found"}, status=404)


def start_server(port=8080, host="127.0.0.1"):
    server_address = (host, port)
    httpd = http.server.HTTPServer(server_address, QuBuggerHandler)
    print(f"QuBugger Web Server running at http://{host}:{port}/")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        httpd.server_close()


if __name__ == "__main__":
    port = 8080
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    start_server(port=port)
