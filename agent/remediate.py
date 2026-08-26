#!/usr/bin/env python3
"""MVP-1 remediation agent.

The agent works only inside the supplied workspace. In production, replace the
heuristic diagnosis with an LLM/Foundry tool-calling adapter, while keeping
this deterministic safety layer around file edits and Terraform commands.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

MAX_FILE_BYTES = 200_000
ALLOWED_EXTENSIONS = {".tf", ".tfvars", ".yaml", ".yml", ".json"}


def run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return p.returncode, p.stdout[-30_000:]


def collect(workspace: Path, log: str) -> dict:
    files = []
    for p in sorted(workspace.rglob("*")):
        if p.is_file() and p.suffix in ALLOWED_EXTENSIONS and p.stat().st_size <= MAX_FILE_BYTES:
            files.append(str(p.relative_to(workspace)))
    return {"failure_log": log[-30_000:], "files": files}


def diagnose(log: str) -> dict:
    if "local-exec" in log and "THIS_FILE_DOES_NOT_EXIST" in log:
        return {
            "category": "TF_APPLY_PROVISIONER_FAILURE",
            "confidence": 0.99,
            "reason": "The null_resource local-exec provisioner is intentionally checking for a file that does not exist.",
            "safe_fix": "replace the intentionally failing deployment gate with a successful deterministic command",
        }
    if "AuthorizationFailed" in log or "does not have authorization" in log:
        return {"category": "CLOUD_PERMISSION", "confidence": 0.97, "reason": "Cloud authorization failure; code changes should not be used as an automatic IAM fix.", "safe_fix": None}
    if "quota" in log.lower() or "SkuNotAvailable" in log:
        return {"category": "CLOUD_QUOTA_OR_SKU", "confidence": 0.90, "reason": "Likely capacity/SKU availability issue; requires risk review.", "safe_fix": None}
    return {"category": "UNKNOWN", "confidence": 0.20, "reason": "No safe MVP rule matched the failure.", "safe_fix": None}


def apply_demo_fix(workspace: Path) -> dict:
    changed = []
    for p in workspace.rglob("*.tf"):
        text = p.read_text()
        old = 'command = "test -f ${path.module}/generated/THIS_FILE_DOES_NOT_EXIST.txt"'
        new = 'command = "test -f ${path.module}/generated/${var.deployment_name}.txt"'
        if old in text:
            backup = p.with_suffix(p.suffix + ".ai-backup")
            backup.write_text(text)
            p.write_text(text.replace(old, new, 1))
            changed.append(str(p.relative_to(workspace)))
    return {"changed_files": changed}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--log", required=True)
    ap.add_argument("--max-attempts", type=int, default=1)
    args = ap.parse_args()

    workspace = Path(args.workspace).resolve()
    log_path = Path(args.log).resolve()
    if not workspace.is_dir() or not log_path.is_file():
        raise SystemExit("workspace or log does not exist")

    log = log_path.read_text(errors="replace")
    evidence = collect(workspace, log)
    diagnosis = diagnose(log)

    result = {
        "agent": "agentic-terraform-mvp1",
        "evidence": evidence,
        "diagnosis": diagnosis,
        "action": "NO_ACTION",
        "validation": {},
    }

    if diagnosis["safe_fix"] is None:
        print(json.dumps(result, indent=2))
        return 2

    fix = apply_demo_fix(workspace)
    result["action"] = "APPLY_DETERMINISTIC_FIX"
    result["fix"] = fix

    if not fix["changed_files"]:
        result["action"] = "NO_SAFE_CHANGE_FOUND"
        print(json.dumps(result, indent=2))
        return 3

    rc_fmt, out_fmt = run(["terraform", "fmt", "-recursive"], workspace)
    rc_validate, out_validate = run(["terraform", "validate"], workspace)
    rc_plan, out_plan = run(["terraform", "plan", "-out=ai-remediation.tfplan"], workspace)
    result["validation"] = {
        "fmt": {"returncode": rc_fmt, "output": out_fmt[-5000:]},
        "validate": {"returncode": rc_validate, "output": out_validate[-10000:]},
        "plan": {"returncode": rc_plan, "output": out_plan[-10000:]},
    }

    print(json.dumps(result, indent=2))
    return 0 if rc_fmt == 0 and rc_validate == 0 and rc_plan == 0 else 4


if __name__ == "__main__":
    raise SystemExit(main())
