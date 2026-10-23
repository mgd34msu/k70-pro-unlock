#!/usr/bin/env python3
"""Fetch checked assets and build exactly the upstream revisions tested here."""
import argparse
from pathlib import Path
import subprocess
import sys
import urllib.request

from k70 import LOCK, ROOT, checked_file, check_tools, require


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tools", type=Path, default=ROOT / "work/tools")
    args = parser.parse_args()
    target = args.tools.resolve()
    target.mkdir(parents=True, exist_ok=True)
    for name, spec in LOCK["downloads"].items():
        path = target / name
        if not path.exists():
            print(f"Downloading {name}", flush=True)
            temporary = path.with_suffix(path.suffix + ".partial")
            try:
                request = urllib.request.Request(spec["url"], headers={"User-Agent": "k70-pro-unlock"})
                with urllib.request.urlopen(request, timeout=90) as response, temporary.open("wb") as dest:
                    import shutil
                    shutil.copyfileobj(response, dest)
                checked_file(temporary, spec["size"], spec["sha256"])
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
        checked_file(path, spec["size"], spec["sha256"])
    for name, spec in LOCK["repositories"].items():
        repo = target / name
        if not repo.exists():
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", spec["url"]], check=True)
            subprocess.run(["git", "-C", str(repo), "fetch", "--depth", "1", "origin", spec["commit"]], check=True)
            subprocess.run(["git", "-C", str(repo), "checkout", "--detach", "FETCH_HEAD"], check=True)
        revision = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
        require(revision == spec["commit"], f"{repo}: refusing to replace unexpected checkout")
        require(not subprocess.check_output(["git", "-C", str(repo), "diff", "HEAD", "--"], text=True), f"{repo}: source modified")
        subprocess.run(["make", "-C", str(repo)], check=True)
    check_tools(target)
    print("Ready. Nothing connected to, rebooted, or flashed a tablet.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"STOP: {exc}", file=sys.stderr)
        sys.exit(1)
