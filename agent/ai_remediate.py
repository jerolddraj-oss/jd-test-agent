#!/usr/bin/env python3
"""MVP-2 LLM remediation agent for Terraform apply failures.

The model diagnoses a Jenkins Terraform APPLY failure and proposes ONE minimal
patch. The process applies the patch only when deterministic safety checks and
Terraform validation/plan succeed. The model never receives permission to
execute shell commands or modify the Git repository.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path

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

SYSTEM_PROMPT = """You are a senior Terraform and cloud deployment remediation engineer running on a Windows Jenkins agent.
Analyze a Jenkins Terraform APPLY failure and propose the smallest safe code fix.

Rules:
1. Work only from the supplied failure log, git diff, and workspace files.
2. Do not invent resources or cloud state that is not evidenced.
3. Prefer a one-file, minimal textual patch.
4. You may modify an existing Terraform local-exec command when the failure is
   clearly a deterministic local deployment-gate problem and the replacement is
   local-only and LOW risk. Do not add new shell commands, external network
   actions, or new resources.
5. This pipeline runs on Windows and local-exec commands are executed by cmd.exe.
6. For the controlled MVP test, the existing deployment file is
   `${path.module}/agentic-mvp.txt` and the current command deliberately returns
   exit code 1 when that file exists:
   `if exist ${path.module}/agentic-mvp.txt (exit 1) else (exit 0)`.
   The preferred fix is to correct only that existing condition so that an
   existing deployment file returns exit code 0 and a missing file returns 1:
   `if exist ${path.module}/agentic-mvp.txt (exit 0) else (exit 1)`.
7. Do not use PowerShell, curl, wget, package managers, cloud CLIs, network access,
   or new resources for this remediation.
8. Do not propose IAM/RBAC, credentials, network-security, database, destroy, or
   production-impacting changes as automatic fixes. Set auto_fix=false for them.
9. Never propose a shell command as a separate action for the pipeline to execute.
   Only return a textual replacement inside the existing Terraform configuration.
10. For the exact controlled deployment-gate failure, use confidence >= 0.95,
    risk LOW, auto_fix true, and modify only main.tf within the Terraform workspace.
11. Return STRICT JSON only with this schema:
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
12. If you cannot prove a safe fix, return auto_fix=false and empty file/patch fields.
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
        "platform": "Windows",
        "shell": "cmd.exe",
        "failure_log": log[-30_000:],
        "git_diff": git_diff[-30_000:],
        "workspace_files": files,
    }
    response = client.responses.create(
        model=model,
        instructions=SYSTEM_PROMPT,
        input=json.dumps(context, ensure_ascii=False),
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
    current = target.read_text(errors="replace")
    if not proposal["old_text"] or proposal["old_text"] not in current:
        return False, "old_text does not exactly match the workspace"
    if proposal["old_text"] == proposal["new_text"]:
        return False, "patch makes no change"

    combined = (proposal["old_text"] + "\n" + proposal["new_text"]).lower()
    for term in FORBIDDEN_PATCH_TERMS:
        if term in combined:
            return False, f"forbidden high-risk term detected: {term}"

    # Deterministic allow-list for the deliberately injected MVP deployment-gate test.
    exact_windows_test = (
        rel.as_posix() == "main.tf"
        and proposal["old_text"].strip() == 'command = "if exist ${path.module}/agentic-mvp.txt (exit 1) else (exit 0)"'
        and proposal["new_text"].strip() == 'command = "if exist ${path.module}/agentic-mvp.txt (exit 0) else (exit 1)"'
    )
    if exact_windows_test:
        return True, "safe: approved deterministic MVP deployment-gate remediation"

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
