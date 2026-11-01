#!/usr/bin/env bash
# Installs the optional non-Python analyzers (ESLint + security plugin, Checkstyle) and reports what ReviewAI can use.
# Run with your virtualenv active:  bash tools/setup.sh      Exit 0 = all available, 1 = something missing.
set -uo pipefail
TOOLS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$TOOLS_DIR")"
CHECKSTYLE_URL="https://github.com/checkstyle/checkstyle/releases/download/checkstyle-10.18.2/checkstyle-10.18.2-all.jar"
problems=()

if command -v node >/dev/null && command -v npm >/dev/null; then
  (cd "$TOOLS_DIR/js" && npm install --no-audit --no-fund) || problems+=("npm install failed in tools/js (ESLint not installed)")
else
  problems+=("Node.js/npm not found: JavaScript/TypeScript analysis unavailable (install Node 20+)")
fi

if command -v java >/dev/null; then
  if curl -fsSL -o "$TOOLS_DIR/java/checkstyle.jar" "$CHECKSTYLE_URL"; then
    java -jar "$TOOLS_DIR/java/checkstyle.jar" --version || problems+=("Checkstyle downloaded but does not run (need Java 11+)")
  else
    problems+=("Could not download Checkstyle")
  fi
else
  problems+=("Java not found: Java analysis unavailable (install a JRE 11+)")
fi

if command -v cppcheck >/dev/null || { [ -n "${CPPCHECK_PATH:-}" ] && [ -f "$CPPCHECK_PATH" ]; }; then
  echo "cppcheck: found"
else
  problems+=("cppcheck not found: C++ analysis unavailable (apt install cppcheck / brew install cppcheck)")
fi

echo; echo "Analyzer availability as seen by ReviewAI:"
(cd "$BACKEND_DIR" && python -c "import json; from app import analysis; print(json.dumps(analysis.availability(), indent=2))") \
  || problems+=("Could not run the backend check: activate your virtualenv and run 'pip install -r requirements.txt' first")

if [ ${#problems[@]} -gt 0 ]; then
  echo "WARNING: some analyzers are NOT available (ReviewAI reports them as unavailable and never fakes a scan):" >&2
  printf '  - %s\n' "${problems[@]}" >&2
  exit 1
fi
echo; echo "All analyzers are available."
