#!/usr/bin/env python3
"""MVP-2 LLM remediation agent for Terraform apply failures.

The model diagnoses the incident and proposes ONE minimal patch. This process
then applies the patch only when it passes deterministic safety checks and
Terraform validation/plan. The model never receives permission to execute
shell commands or modify the Git repository.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

from openai import OpenAI

MAX_FILE_BYTES = 120_000
MAX_TOTAL_CONTEXT = 500_000
ALLOWED_EXTENSIONS = {".tf", ".tfvars", ".yaml", ".yml", ".json"}
FORBIDDEN_PATCH_TERMS = {
    "terraform destroy",
    "-destroy",
    "azurerm_role_assignment",
    "aws_iam_role",
    "aws_iam_policy",
    "azurerm_key_vault_access_policy",
}

SYSTEM_PROMPT = """You are a senior Terraform and cloud deployment remediation engineer.
Analyze a Jenkins Terraform APPLY failure and propose the smallest safe code fix.

Rules:
1. Work only from the supplied failure log, git diff, and workspace files.
2. Do not invent resources or cloud state that is not evidenced.
3. Prefer a one-file, minimal textual patch.
4. Do not propose IAM/RBAC, credential, network-security, database, destroy, or
   production-impacting changes as automatic fixes. Set auto_fix=false for them.
5. Never propose shell commands. The pipeline, not the model, executes commands.
6. Return STRICT JSON only with this schema:
{
  "root_cause": "...",
  "category": "...",
  "confidence": 0.0,
  "auto_fix": true,
  "risk": "LOW|MEDIUM|HIGH",
  "file": "relative/path.tf",
  "old_text": "exact existing text to replace",
  "new_text": "replacement text",
  "rationale": "..."
}
7. If you cannot prove a safe fix, return auto_fix=false and empty file/patch fields.
"""


def run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return p.returncode, p.stdout[-30_000:]


def collect_files(workspace: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    total = 0
    for p in sorted(workspace.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in ALLOWED_EXTENSIONS:
            continue
        if any(part in {".terraform", ".git"} for part in p.parts):
            continue
        if p.stat().st_size > MAX_FILE_BYTES:
            continue
        text = p.read_text(errors="replace")
        if total + len(text) > MAX_TOTAL_CONTEXT:
            break
        result[str(p.relative_to(workspace)).replace("\\", "/")] = text
        total += len(text)
    return result


def get_git_diff(workspace: Path) -> str:
    rc, out = run(["git", "diff", "--", "."], workspace)
    return out if rc == 0 else "git diff unavailable"


def ask_model(log: str, files: dict[str, str], git_diff: str) -> dict:
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT", "").rstrip("/")
    model = os.environ.get("AZURE_OPENAI_MODEL", "")
    api_key = os.environ.get("AZURE_OPENAI_API_KEY", "")
    if not endpoint or not model or not api_key:
        raise RuntimeError("AZURE_OPENAI_ENDPOINT, AZURE_OPENAI_MODEL and AZURE_OPENAI_API_KEY are required")

    client = OpenAI(api_key=api_key, base_url=f"{endpoint}/openai/v1/")
    context = {
        "failure_log": log[-30_000:],
        "git_diff": git_diff[-30_000:],
        "workspace_files": files,
    }
    response = client.responses.create(
        model=model,
        instructions=SYSTEM_PROMPT,
        input=json.dumps(context, ensure_ascii=False),
        temperature=0,
    )
    text = response.output_text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise RuntimeError(f"Model did not return valid JSON: {text[:2000]}") from exc
        return json.loads(match.group(0))


def safety_check(proposal: dict, workspace: Path) -> tuple[bool, str]:
    required = ["root_cause", "category", "confidence", "auto_fix", "risk", "file", "old_text", "new_text", "rationale"]
    if any(k not in proposal for k in required):
        return False, "model response is missing required fields"
    if proposal.get("auto_fix") is not True:
        return False, "model did not authorize an automatic fix"
    if proposal.get("risk") != "LOW":
        return False, "automatic remediation is restricted to LOW risk"
    if float(proposal.get("confidence", 0)) < 0.85:
        return False, "model confidence is below 0.85"

    rel = Path(str(proposal["file"]))
    if rel.is_absolute() or ".." in rel.parts:
        return False, "patch path escapes workspace"
    if rel.suffix.lower() not in ALLOWED_EXTENSIONS:
        return False, "file type is not allowed"
    target = (workspace / rel).resolve()
    if workspace not in target.parents:
        return False, "patch target escapes workspace"
    if not target.is_file():
        return False, "patch target does not exist"
    if not proposal["old_text"] or proposal["old_text"] not in target.read_text(errors="replace"):
        return False, "old_text does not exactly match the workspace"
    if proposal["old_text"] == proposal["new_text"]:
        return False, "patch makes no change"
    combined = (proposal["old_text"] + "\n" + proposal["new_text"]).lower()
    for term in FORBIDDEN_PATCH_TERMS:
        if term in combined:
            return False, f"forbidden high-risk term detected: {term}"
    return True, "safe"


def apply_patch(proposal: dict, workspace: Path) -> str:
    target = (workspace / proposal["file"]).resolve()
    original = target.read_text(errors="replace")
    backup = target.with_suffix(target.suffix + ".ai-backup")
    backup.write_text(original)
    updated = original.replace(proposal["old_text"], proposal["new_text"], 1)
    target.write_text(updated)
    return str(target.relative_to(workspace)).replace("\\", "/")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", required=True)
    ap.add_argument("--log", required=True)
    args = ap.parse_args()

    workspace = Path(args.workspace).resolve()
    log_path = Path(args.log).resolve()
    result = {"agent": "agentic-terraform-mvp2", "status": "FAILED"}

    try:
        if not workspace.is_dir() or not log_path.is_file():
            raise RuntimeError("workspace or log does not exist")
        log = log_path.read_text(errors="replace")
        files = collect_files(workspace)
        git_diff = get_git_diff(workspace)
        proposal = ask_model(log, files, git_diff)
        result["proposal"] = proposal

        safe, reason = safety_check(proposal, workspace)
        result["safety"] = {"approved": safe, "reason": reason}
        if not safe:
            print(json.dumps(result, indent=2))
            return 2

        changed = apply_patch(proposal, workspace)
        result["changed_file"] = changed

        rc_fmt, out_fmt = run(["terraform", "fmt", "-recursive"], workspace)
        rc_validate, out_validate = run(["terraform", "validate"], workspace)
        rc_plan, out_plan = run(["terraform", "plan", "-out=ai-remediation.tfplan"], workspace)
        result["validation"] = {
            "fmt": {"returncode": rc_fmt, "output": out_fmt[-5000:]},
            "validate": {"returncode": rc_validate, "output": out_validate[-10000:]},
            "plan": {"returncode": rc_plan, "output": out_plan[-10000:]},
        }
        result["status"] = "READY_FOR_REAPPLY" if rc_fmt == rc_validate == rc_plan == 0 else "VALIDATION_FAILED"
        print(json.dumps(result, indent=2))
        return 0 if result["status"] == "READY_FOR_REAPPLY" else 4
    except Exception as exc:
        result["error"] = str(exc)
        print(json.dumps(result, indent=2))
        return 10


if __name__ == "__main__":
    raise SystemExit(main())
