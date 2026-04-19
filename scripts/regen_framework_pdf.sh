#!/usr/bin/env bash
# Regenerate docs/FRAMEWORK_AND_PIPELINE.pdf from docs/FRAMEWORK_AND_PIPELINE.md.
#
# Why this script exists (RALPH iron rules 5 and 6):
#   Iron rule 5 — never silence tooling. If md-to-pdf fails, fix the cause,
#     do not add flags to hide it. This script exits non-zero on any step.
#   Iron rule 6 — every research-relevant artifact is hash-logged. After
#     regeneration we print the SHA-256 of the produced PDF so an auditor
#     can trace docs/FRAMEWORK_AND_PIPELINE.pdf back to the specific commit
#     that produced it.
#
# Puppeteer launch flags live in config/puppeteer.config.js, not on the
# command line. That file is the single source of truth; see its header
# comment for why each flag is needed. This script must not pass
# --launch-options in parallel — one or the other, never both.
#
# Usage:
#   scripts/regen_framework_pdf.sh
#
# Completion criterion 8 (docs/RALPH_LOOP_TASK.md):
#   "docs/FRAMEWORK_AND_PIPELINE.pdf has been regenerated today via
#    scripts/regen_framework_pdf.sh and committed."

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

INPUT_MD="docs/FRAMEWORK_AND_PIPELINE.md"
OUTPUT_PDF="docs/FRAMEWORK_AND_PIPELINE.pdf"
CONFIG="config/puppeteer.config.js"

if [ ! -f "$INPUT_MD" ]; then
  echo "ERROR: input markdown not found: $INPUT_MD" >&2
  exit 1
fi
if [ ! -f "$CONFIG" ]; then
  echo "ERROR: puppeteer config not found: $CONFIG" >&2
  exit 1
fi
if ! command -v md-to-pdf >/dev/null 2>&1; then
  echo "ERROR: md-to-pdf not on PATH. Install: npm install -g md-to-pdf" >&2
  exit 1
fi

echo "==> Regenerating $OUTPUT_PDF from $INPUT_MD"
echo "    md-to-pdf: $(md-to-pdf --version 2>/dev/null || echo 'unknown')"
echo "    config:    $CONFIG"

# md-to-pdf reads launch_options and pdf_options from --config-file.
md-to-pdf "$INPUT_MD" --config-file "$CONFIG"

if [ ! -f "$OUTPUT_PDF" ]; then
  echo "ERROR: md-to-pdf exited 0 but $OUTPUT_PDF was not produced" >&2
  exit 1
fi

PDF_BYTES=$(stat -c%s "$OUTPUT_PDF")
PDF_SHA=$(sha256sum "$OUTPUT_PDF" | awk '{print $1}')

echo "==> Regeneration complete"
echo "    path:   $OUTPUT_PDF"
echo "    bytes:  $PDF_BYTES"
echo "    sha256: $PDF_SHA"
