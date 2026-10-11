#!/usr/bin/env python3
"""Fake `claude` for tests. Controlled by FAKE_CLAUDE_* env vars."""
import json
import os
import sys
import time

def _prompt_file():
    if "--system-prompt-file" in sys.argv:
        with open(sys.argv[sys.argv.index("--system-prompt-file") + 1], encoding="utf-8") as f:
            return f.read()
    return None


data = sys.stdin.read()
log = os.environ.get("FAKE_CLAUDE_LOG")
if log:
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps({"argv": sys.argv[1:], "stdin": data, "inner": os.environ.get("UGETME_INNER"),
                            "no_mds": os.environ.get("CLAUDE_CODE_DISABLE_CLAUDE_MDS"),
                            "config_dir": os.environ.get("CLAUDE_CONFIG_DIR"),
                            "system_prompt": _prompt_file(),
                            "creds": sorted(k for k in os.environ if (k.startswith(("ANTHROPIC_", "CLAUDE_CODE_")) or k == "CLAUDECODE") and k != "CLAUDE_CODE_DISABLE_CLAUDE_MDS"),
                            "base_url": os.environ.get("ANTHROPIC_BASE_URL"),
                            "path": os.environ.get("PATH", "")}) + "\n")
mode = os.environ.get("FAKE_CLAUDE_MODE", "ok")
if mode == "fail":
    sys.stderr.write("Error: not logged in\n")
    sys.exit(1)
if mode == "reject_effort" and "--effort" in sys.argv:
    sys.stderr.write("error: unknown option '--effort'\n")
    sys.exit(1)
if mode == "sleep":
    time.sleep(5)
if mode == "garbage":
    print("sorry, I cannot help")
    sys.exit(0)
print(os.environ.get("FAKE_CLAUDE_OUT", json.dumps({"clean": "Clean text.", "unclear": None})))
