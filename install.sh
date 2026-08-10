#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
BIN_DIR="$HOME/.local/bin"
TARGET="$BIN_DIR/healthy"
UV_BIN="$(command -v uv || true)"

if [[ -z "$UV_BIN" ]]; then
  echo "error: uv is required to install healthy" >&2
  echo "install uv from https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
fi

mkdir -p "$BIN_DIR"
"$UV_BIN" sync --locked --project "$PROJECT_DIR"

PROJECT_DIR_ESCAPED="$(printf '%q' "$PROJECT_DIR")"
UV_BIN_ESCAPED="$(printf '%q' "$UV_BIN")"
cat > "$TARGET" <<EOF
#!/usr/bin/env bash
set -euo pipefail
exec $UV_BIN_ESCAPED run --locked --project $PROJECT_DIR_ESCAPED healthy "\$@"
EOF
chmod +x "$TARGET"

echo "Installed healthy to $TARGET"
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
  echo "Add this to your shell profile to call healthy from anywhere:"
  echo "  export PATH=\"$BIN_DIR:\$PATH\""
fi
