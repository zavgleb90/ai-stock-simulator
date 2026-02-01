# simulator/cli_parse_issue_body.py
from __future__ import annotations

import argparse
from pathlib import Path

from .github_issue_parser import parse_order_from_issue_body

def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--file", required=True, help="Path to a text file containing the GitHub issue body.")
    args = p.parse_args()

    body = Path(args.file).read_text(encoding="utf-8")
    order = parse_order_from_issue_body(body)
    print(order)

if __name__ == "__main__":
    main()
