from __future__ import annotations
import base64
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

REPO = os.getenv("INTEL_BOTTLE_REPO", "louisje/homebrew-intel-bottles")
BREW = os.getenv("INTEL_BOTTLE_BREW", "/usr/local/bin/brew")
INVENTORY_PATH = ".github/runner-inventory/imac-intel.json"
CACHE = Path.home() / ".cache" / "brew-intel-bottle" / "inventory.json"

def snapshot():
    result = subprocess.run([BREW, "list", "--formula", "--versions"], capture_output=True, text=True, check=True)
    formulas = {}
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            formulas[parts[0]] = parts[1:]
    return {"schema": 1, "runner": "imac-intel", "updated_at": datetime.now(timezone.utc).isoformat(), "formulae": formulas}

def github(*args, input_text=None):
    p = subprocess.run(["gh", "api", *args], input=input_text, text=True, capture_output=True)
    if p.returncode:
        raise RuntimeError(p.stderr.strip() or "GitHub API failed")
    return json.loads(p.stdout) if p.stdout.strip() else {}

def run(args):
    if args not in ([], ["--sync"], ["--status"]):
        print("usage: brew intel-bottle inventory [--sync|--status]", file=sys.stderr)
        return 2
    if args == ["--status"]:
        if not CACHE.exists():
            print("No local inventory snapshot")
            return 0
        data = json.loads(CACHE.read_text())
        print(f"Last local snapshot: {data['updated_at']} ({len(data['formulae'])} formulae)")
        return 0
    data = snapshot()
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    if args != ["--sync"]:
        print(json.dumps(data, indent=2, sort_keys=True))
        return 0
    path = f"repos/{REPO}/contents/{INVENTORY_PATH}"
    try:
        existing = github(path)
        sha = existing.get("sha")
        if sha:
            previous = json.loads(base64.b64decode(existing["content"]).decode())
            if previous.get("formulae") == data["formulae"]:
                print("Inventory unchanged; no upload needed")
                return 0
    except RuntimeError as exc:
        if "404" not in str(exc):
            raise
        sha = None
    payload = {"message": "chore(inventory): refresh imac-intel Homebrew formulae", "content": base64.b64encode((json.dumps(data, indent=2, sort_keys=True) + "\n").encode()).decode()}
    if sha:
        payload["sha"] = sha
    github("-X", "PUT", path, "--input", "-", input_text=json.dumps(payload))
    print(f"Synced {len(data['formulae'])} formulae to {REPO}")
    return 0
