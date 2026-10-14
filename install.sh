#!/usr/bin/env bash
# Inbox Warden installer: downloads the app, asks for your keys, starts it and opens it in your browser.
#   curl -fsSL https://raw.githubusercontent.com/IshanVats-6/inbox-warden/main/install.sh | bash
set -euo pipefail

REPO="https://github.com/IshanVats-6/inbox-warden"
DIR="${INBOX_WARDEN_DIR:-$HOME/inbox-warden}"

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
info() { printf '\033[38;5;99m›\033[0m %s\n' "$*"; }
ok() { printf '\033[32m✓\033[0m %s\n' "$*"; }
die() { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }
# read from the terminal even when this script is piped into bash
ask() { local prompt="$1" default="${2:-}" reply; read -r -p "  $prompt${default:+ [$default]}: " reply </dev/tty; echo "${reply:-$default}"; }
ask_secret() { local reply; read -r -s -p "  $1: " reply </dev/tty; echo >&2; echo "$reply"; }
rand() { (LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c "$1") || true; }  # head closes the pipe early; ignore SIGPIPE
port_free() { ! (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }

echo
bold "  📬  Inbox Warden"
echo "  An AI agent that labels and cleans your Gmail inboxes."
echo

# ---------- prerequisites ----------
command -v git >/dev/null || die "git is required. Install it and run this again."
RUNNER=""
if command -v docker >/dev/null && docker info >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  RUNNER="docker"
elif command -v python3 >/dev/null && python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
  RUNNER="python"
  info "Docker isn't running, so Inbox Warden will run with Python $(python3 -c 'import platform; print(platform.python_version())')."
else
  die "Install Docker Desktop (recommended) or Python 3.10+, then run this again."
fi

# ---------- download ----------
if [ -d "$DIR/.git" ]; then
  info "Updating $DIR"
  git -C "$DIR" pull --quiet --ff-only
else
  info "Downloading to $DIR"
  git clone --quiet --depth 1 "$REPO" "$DIR"
fi
cd "$DIR"

# ---------- configuration ----------
if [ -f .env ] && [ "$(ask 'Found an existing setup. Keep it? (Y/n)' Y)" != "n" ]; then
  ok "Keeping your existing settings"
  # shellcheck disable=SC1091
  set -a; . ./.env; set +a
else
  echo
  bold "  1. AI keys"
  echo "  Inbox Warden uses Jev (TypeSafe) for fast labeling and Claude to create new labels."
  echo "  Jev key:    https://console.typesafe.ai"
  echo "  Claude key: https://console.anthropic.com/settings/keys"
  TYPESAFE_API_KEY=$(ask_secret "Jev (TypeSafe) API key")
  ANTHROPIC_API_KEY=$(ask_secret "Claude (Anthropic) API key")
  [ -n "$TYPESAFE_API_KEY$ANTHROPIC_API_KEY" ] || die "At least one AI key is needed."
  [ -n "$ANTHROPIC_API_KEY" ] || info "No Claude key: Inbox Warden will only use existing labels and won't create new ones."

  PORT=8080
  while ! port_free "$PORT"; do PORT=$((PORT + 1)); done

  echo
  bold "  2. Google sign-in (to connect your Gmail)"
  echo "  Create an OAuth client in your own Google Cloud project (5 minutes):"
  echo "  $REPO/blob/main/docs/google-setup.md"
  echo "  Use this as the Authorized redirect URI:  http://localhost:$PORT/oauth/callback"
  GOOGLE_CLIENT_ID=$(ask "Google OAuth Client ID")
  GOOGLE_CLIENT_SECRET=$( [ -n "$GOOGLE_CLIENT_ID" ] && ask_secret "Google OAuth Client secret" || true )
  [ -n "$GOOGLE_CLIENT_ID" ] || info "Skipped. Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to $DIR/.env later to connect mailboxes."

  TZ_GUESS=$( (readlink /etc/localtime 2>/dev/null | sed 's#.*/zoneinfo/##') || true )
  echo
  bold "  3. Schedule"
  TZ_VALUE=$(ask "Your timezone" "${TZ_GUESS:-UTC}")

  ADMIN_PASSWORD=$(rand 16)
  umask 077
  cat > .env <<EOF
PUBLIC_URL=http://localhost:$PORT
PORT=$PORT
ADMIN_PASSWORD=$ADMIN_PASSWORD
SECRET_KEY=$(rand 48)
TYPESAFE_API_KEY=$TYPESAFE_API_KEY
ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY
GOOGLE_CLIENT_ID=$GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET=$GOOGLE_CLIENT_SECRET
TZ=$TZ_VALUE
SCHEDULE="0 7,14,19 * * *"
EOF
  ok "Saved settings to $DIR/.env"
fi

# ---------- start ----------
echo
if [ "$RUNNER" = "docker" ]; then
  info "Building and starting (first run takes a minute)"
  docker compose up -d --build --quiet-pull >/dev/null
else
  info "Installing Python packages (first run takes a minute)"
  [ -d .venv ] || python3 -m venv .venv
  .venv/bin/pip install --quiet --upgrade pip >/dev/null
  .venv/bin/pip install --quiet -r requirements.txt
  [ -f .warden.pid ] && kill "$(cat .warden.pid)" 2>/dev/null || true
  (set -a; . ./.env; set +a; DATA_DIR="$DIR/data" nohup .venv/bin/uvicorn warden.app:app --host 127.0.0.1 --port "$PORT" \
    >"$DIR/warden.log" 2>&1 & echo $! >.warden.pid)
fi

URL="http://localhost:$PORT"
for _ in $(seq 1 90); do curl -fsS "$URL/health" >/dev/null 2>&1 && break; sleep 2; done
if ! curl -fsS "$URL/health" >/dev/null 2>&1; then
  [ "$RUNNER" = "docker" ] && die "Inbox Warden didn't start. See: cd $DIR && docker compose logs"
  die "Inbox Warden didn't start. See: $DIR/warden.log"
fi

echo
ok "Inbox Warden is running at $URL"
echo "    Password: $ADMIN_PASSWORD"
echo
echo "  Next: Mailboxes → Connect with Google, then Settings → describe your company, then Preview run."
if [ "$RUNNER" = "docker" ]; then
  echo "  Stop: cd $DIR && docker compose down      Update: run this installer again"
else
  echo "  Stop: kill \$(cat $DIR/.warden.pid)          Update: run this installer again"
fi
echo
(command -v open >/dev/null && open "$URL") || (command -v xdg-open >/dev/null && xdg-open "$URL" >/dev/null 2>&1) || true
