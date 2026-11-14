"""Small high-confidence regression guard; not a substitute for manual OWASP review."""
import ast
from pathlib import Path
import re
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
result = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=root, check=True, capture_output=True)
names = sorted(set(result.stdout.decode().split("\0"))-{ "" })
secrets = re.compile(r"-----BEGIN\s+(?:RSA\s+|EC\s+|OPENSSH\s+)?PRIVATE\s+KEY-----|SG\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}|FLWSECK-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}|gh[pousr]_[A-Za-z0-9]{30,}")
issues = []
scanned = 0
for name in names:
    path = root / name
    if not path.is_file() or path.suffix not in {".py", ".html", ".js", ".md", ".yml", ".yaml", ".txt", ".example"}:
        continue
    if name.startswith("static/") and name not in {"static/js/dashboard.js", "static/js/login.js", "static/js/main.js"}:
        continue  # Third-party distributions have a separate dependency review.
    source = path.read_text(encoding="utf-8-sig")
    scanned += 1
    for number, line in enumerate(source.splitlines(), 1):
        if secrets.search(line):
            issues.append((name, number, "possible-secret"))
    if path.suffix == ".py":
        tree = ast.parse(source, filename=name)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            function = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ""
            if function in {"eval", "exec", "mark_safe"}:
                issues.append((name, node.lineno, "unsafe-code-or-html"))
            if function in {"execute", "executemany", "raw"} and "/migrations/" not in name and not path.name.startswith("test") and node.args and isinstance(node.args[0], (ast.JoinedStr, ast.BinOp)):
                issues.append((name, node.lineno, "interpolated-sql-review-required"))
            if any(keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True for keyword in node.keywords):
                issues.append((name, node.lineno, "shell-execution"))
    if path.suffix == ".html":
        for match in re.finditer(r"<script\b([^>]*)>", source, re.I):
            attributes = match.group(1)
            if "src=" not in attributes and "nonce=" not in attributes and "application/json" not in attributes:
                issues.append((name, source.count("\n", 0, match.start())+1, "inline-script-without-nonce"))
for name, number, code in issues:
    print(f"{name}:{number}: {code}")  # Never echo a suspected secret's value.
if issues:
    sys.exit(1)
print(f"Security regression scan passed for {scanned} source/documentation files.")
