#!/usr/bin/env python3
"""Check repository documentation links and evidence metadata without editing files."""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = ["doc/README.md", "doc/goal.md", "doc/plan/implementation.md",
            "doc/plan/backlog.md", "doc/prototype/specification.md",
            "doc/requirements/acceptance.md", "doc/architecture/system.md",
            "doc/api/contracts.md", "doc/qa/quality-gates.md", "doc/qa/test-plan.md",
            "doc/qa/gates.json", "doc/development/worktrees.md",
            "doc/deployment/runbook.md", "doc/delivery/release-template.md"]

def main():
    errors = []
    for name in REQUIRED:
        if not (ROOT / name).is_file():
            errors.append(f"Missing required document: {name}")
    documents = [ROOT / "README.md", *sorted((ROOT / "doc").rglob("*.md"))]
    if (ROOT / "AGENTS.md").exists():
        documents.append(ROOT / "AGENTS.md")
    for path in documents:
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8")
        content = re.sub(r"```.*?```", "", content, flags=re.S)
        for target in re.findall(r"(?<!!)\[[^\]]+\]\(([^)]+)\)", content):
            target = target.strip().strip("<>").split("#", 1)[0]
            if not target or re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", target):
                continue
            if target.startswith("/") or not (path.parent / target).exists():
                errors.append(f"{path.relative_to(ROOT)}: invalid local link {target}")
    try:
        data = json.loads((ROOT / "doc/qa/gates.json").read_text())
        gates = data["gates"]
        if data["schema_version"] != 1 or sorted(g["id"] for g in gates) != sorted(["P0", "G1", "G2", "G3", "G4", "G5", "G6"]):
            errors.append("Unexpected gate schema or gate IDs")
        for gate in gates:
            if gate["status"] not in {"NOT_RUN", "PASS", "FAIL"}:
                errors.append(f"Invalid status: {gate['id']}")
            if gate["status"] in {"PASS", "FAIL"}:
                if not all(gate.get(key) for key in ("checked_at", "commit", "evidence")):
                    errors.append(f"Missing evidence metadata: {gate['id']}")
                    continue
                evidence = ROOT / "doc/qa" / gate["evidence"]
                if not evidence.resolve().is_relative_to((ROOT / "doc/qa").resolve()) or not evidence.is_file():
                    errors.append(f"Missing or unsafe evidence: {gate['id']}")
                valid = subprocess.run(["git", "rev-parse", "--verify", gate["commit"] + "^{commit}"], cwd=ROOT, capture_output=True)
                if valid.returncode:
                    errors.append(f"Unknown evidence commit: {gate['id']}")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        errors.append(f"Invalid gate registry: {exc}")
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print(f"PASS: {len(documents)} Markdown documents; local links and gate metadata valid. Application gates are not executed.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
