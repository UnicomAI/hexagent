#!/bin/bash
# =============================================================================
# HexAgent VM Setup - Orchestrator
# =============================================================================
# Discovers and runs step scripts in order with progress reporting,
# resumability (marker files), concurrency protection (flock), and
# heartbeat for long-running operations.
#
# Usage:
#   sudo bash setup.sh              # Run all steps (skip completed)
#   sudo bash setup.sh --force      # Re-run all steps ignoring markers
#   sudo bash setup.sh --step 05_pip  # Run a single step
#   sudo bash setup.sh --list       # Show step status
#   sudo bash setup.sh --reset      # Clear all markers
#
# Progress protocol (stdout):
#   @@SETUP:<step_id>:<status>:<message>
#   Statuses: start, progress, done, skip, error, heartbeat
# =============================================================================

set -uo pipefail
# No -e: we handle errors per-step.

# ------ Constants ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
STEPS_DIR="${SCRIPT_DIR}/steps"
MARKER_DIR="/var/lib/hexagent/setup"
LOG_DIR="/var/log/hexagent/setup"
LOCK_FILE="/var/run/hexagent-setup.lock"
LOCK_FD=9

# ------ Environment (inherited by steps) ------------------------------------------------------------------------------------------------------------------------
export DEBIAN_FRONTEND=noninteractive
export PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers
export MARKER_DIR LOG_DIR
if grep -qi microsoft /proc/version 2>/dev/null; then
    _OPENAGENT_DEFAULT_CN_MIRRORS=1
else
    _OPENAGENT_DEFAULT_CN_MIRRORS=0
fi
OPENAGENT_USE_CN_MIRRORS="${OPENAGENT_USE_CN_MIRRORS:-${_OPENAGENT_DEFAULT_CN_MIRRORS}}"
OPENAGENT_APT_MIRROR="${OPENAGENT_APT_MIRROR:-https://mirrors.ustc.edu.cn/ubuntu}"
OPENAGENT_APT_PORTS_MIRROR="${OPENAGENT_APT_PORTS_MIRROR:-https://mirrors.ustc.edu.cn/ubuntu-ports}"
OPENAGENT_PIP_INDEX_URL="${OPENAGENT_PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
OPENAGENT_NPM_REGISTRY="${OPENAGENT_NPM_REGISTRY:-https://registry.npmmirror.com}"
OPENAGENT_PLAYWRIGHT_DOWNLOAD_HOST="${OPENAGENT_PLAYWRIGHT_DOWNLOAD_HOST:-https://npmmirror.com/mirrors/playwright}"
export OPENAGENT_USE_CN_MIRRORS OPENAGENT_APT_MIRROR OPENAGENT_APT_PORTS_MIRROR
export OPENAGENT_PIP_INDEX_URL OPENAGENT_NPM_REGISTRY OPENAGENT_PLAYWRIGHT_DOWNLOAD_HOST

# ------ CLI defaults ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
FORCE=false
SINGLE_STEP=""
LIST_ONLY=false
RESET=false

# ------ CLI parsing ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
usage() {
    echo "Usage: sudo bash setup.sh [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --force       Re-run all steps (ignore markers)"
    echo "  --step <id>   Run a single step (e.g. --step 05_pip)"
    echo "  --list        Show steps and their completion status"
    echo "  --reset       Clear all markers, then exit"
    echo "  -h, --help    Show this help"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --force)  FORCE=true; shift ;;
        --step)   SINGLE_STEP="$2"; shift 2 ;;
        --list)   LIST_ONLY=true; shift ;;
        --reset)  RESET=true; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "Unknown option: $1"; usage; exit 1 ;;
    esac
done

# ------ Root check ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
if [[ "$(id -u)" -ne 0 ]]; then
    echo "ERROR: Must run as root (sudo)." >&2
    exit 1
fi

# ------ Directory setup ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
mkdir -p "$MARKER_DIR" "$LOG_DIR"

# ------ emit() -progress protocol ------------------------------------------------------------------------------------------------------------------------------------------
# Writes to fd 3 which points to the original stdout (what the backend reads).
# All other output (package managers) goes to the log file.
emit() {
    # Usage: emit <step_id> <status> <message>
    local step_id="$1" status="$2" message="${3:-}"
    printf '@@SETUP:%s:%s:%s\n' "$step_id" "$status" "$message" >&3
}
export -f emit

# ------ apt_install -retry wrapper ------------------------------------------------------------------------------------------------------------------------------------------
apt_install() {
    local max_attempts=5
    local delay=3
    local attempt=1

    while [[ $attempt -le $max_attempts ]]; do
        echo ">>> apt-get install attempt $attempt/$max_attempts"
        if [[ $attempt -eq 1 ]]; then
            apt-get install -y --no-install-recommends "$@" && return 0
        else
            apt-get install -y --no-install-recommends --fix-missing "$@" && return 0
        fi

        echo ">>> Attempt $attempt failed. Retrying in ${delay}s..."
        sleep $delay
        dpkg --configure -a || true
        apt-get install -y -f || true
        delay=$((delay * 2))
        attempt=$((attempt + 1))
    done

    # Final fallback: per-package download then bulk install
    echo ">>> Bulk install failed. Falling back to per-package download..."
    dpkg --configure -a || true
    apt-get install -y -f || true

    local pkg
    for pkg in "$@"; do
        local pkg_attempt=1
        while [[ $pkg_attempt -le 3 ]]; do
            apt-get install -y --no-install-recommends -d "$pkg" 2>/dev/null && break
            echo ">>> Download failed for $pkg (attempt $pkg_attempt/3)"
            sleep $((pkg_attempt * 2))
            pkg_attempt=$((pkg_attempt + 1))
        done
    done

    echo ">>> Installing all packages from local cache..."
    if apt-get install -y --no-install-recommends "$@"; then
        return 0
    fi

    echo ">>> ERROR: apt-get install failed after all retries"
    echo ">>> Failed packages: $*"
    return 1
}
export -f apt_install

# ------ pip_install -retry wrapper ------------------------------------------------------------------------------------------------------------------------------------------
pip_install() {
    local max_attempts=5
    local delay=5
    local attempt=1
    local use_cn_mirrors="${OPENAGENT_USE_CN_MIRRORS:-0}"
    local pip_opts=(
        --timeout 120
        --retries 3
        --no-cache-dir
    )
    if pip3 help install 2>/dev/null | grep -q -- "--break-system-packages"; then
        pip_opts+=(--break-system-packages)
    fi

    while [[ $attempt -le $max_attempts ]]; do
        echo ">>> pip install attempt $attempt/$max_attempts (${#} packages)"
        if pip3 install "${pip_opts[@]}" "$@"; then
            return 0
        fi
        if [[ "$use_cn_mirrors" == "1" ]]; then
            echo ">>> Mirror install failed, retrying with official PyPI..."
            if PIP_INDEX_URL="https://pypi.org/simple" \
               PIP_EXTRA_INDEX_URL="" \
               pip3 install "${pip_opts[@]}" "$@"; then
                return 0
            fi
        fi
        echo ">>> Attempt $attempt failed. Retrying in ${delay}s..."
        sleep $delay
        delay=$((delay * 2))
        attempt=$((attempt + 1))
    done

    # Final fallback: install one at a time
    echo ">>> Batch install failed. Falling back to per-package install..."
    local pkg failed=()
    for pkg in "$@"; do
        local pkg_attempt=1
        local pkg_ok=false
        while [[ $pkg_attempt -le 3 ]]; do
            if pip3 install "${pip_opts[@]}" "$pkg" 2>&1; then
                pkg_ok=true
                break
            fi
            if [[ "$use_cn_mirrors" == "1" ]]; then
                if PIP_INDEX_URL="https://pypi.org/simple" \
                   PIP_EXTRA_INDEX_URL="" \
                   pip3 install "${pip_opts[@]}" "$pkg" 2>&1; then
                    pkg_ok=true
                    break
                fi
            fi
            echo ">>> Failed: $pkg (attempt $pkg_attempt/3)"
            sleep $((pkg_attempt * 3))
            pkg_attempt=$((pkg_attempt + 1))
        done
        if [[ "$pkg_ok" == false ]]; then
            failed+=("$pkg")
        fi
    done

    if [[ ${#failed[@]} -gt 0 ]]; then
        echo ">>> ERROR: These packages failed after all retries:"
        printf '>>>   %s\n' "${failed[@]}"
        return 1
    fi
    return 0
}
export -f pip_install

configure_cn_mirrors() {
    if [[ "${OPENAGENT_USE_CN_MIRRORS}" != "1" ]]; then
        return 0
    fi

    emit _meta progress "Applying China mirrors (APT/PIP/NPM/Playwright)"

    # sed replacement escapes for arbitrary mirror strings (e.g. containing '&' or '|')
    local apt_mirror_esc apt_ports_mirror_esc
    apt_mirror_esc="${OPENAGENT_APT_MIRROR//\\/\\\\}"
    apt_mirror_esc="${apt_mirror_esc//&/\\&}"
    apt_mirror_esc="${apt_mirror_esc//|/\\|}"
    apt_ports_mirror_esc="${OPENAGENT_APT_PORTS_MIRROR//\\/\\\\}"
    apt_ports_mirror_esc="${apt_ports_mirror_esc//&/\\&}"
    apt_ports_mirror_esc="${apt_ports_mirror_esc//|/\\|}"

    if [[ -f /etc/apt/sources.list ]]; then
        cp -n /etc/apt/sources.list /etc/apt/sources.list.openagent.bak 2>/dev/null || true
        sed -Ei \
            -e "s|https?://(archive|security)\.ubuntu\.com/ubuntu|${apt_mirror_esc}|g" \
            -e "s|https?://ports\.ubuntu\.com/ubuntu-ports|${apt_ports_mirror_esc}|g" \
            /etc/apt/sources.list 2>/dev/null || true
    fi

    if [[ -f /etc/apt/sources.list.d/ubuntu.sources ]]; then
        cp -n /etc/apt/sources.list.d/ubuntu.sources /etc/apt/sources.list.d/ubuntu.sources.openagent.bak 2>/dev/null || true
        sed -Ei \
            -e "s|^URIs:[[:space:]]*https?://(archive|security)\.ubuntu\.com/ubuntu/?$|URIs: ${apt_mirror_esc}|g" \
            -e "s|^URIs:[[:space:]]*https?://ports\.ubuntu\.com/ubuntu-ports/?$|URIs: ${apt_ports_mirror_esc}|g" \
            /etc/apt/sources.list.d/ubuntu.sources 2>/dev/null || true
    fi

    cat >/etc/pip.conf <<EOF
[global]
index-url = ${OPENAGENT_PIP_INDEX_URL}
extra-index-url = https://pypi.org/simple
timeout = 120
retries = 5
EOF

    mkdir -p /etc/profile.d
    cat >/etc/profile.d/openagent-mirrors.sh <<EOF
export OPENAGENT_USE_CN_MIRRORS=1
export PIP_INDEX_URL='${OPENAGENT_PIP_INDEX_URL}'
export NPM_CONFIG_REGISTRY='${OPENAGENT_NPM_REGISTRY}'
export PLAYWRIGHT_DOWNLOAD_HOST='${OPENAGENT_PLAYWRIGHT_DOWNLOAD_HOST}'
EOF
}
export -f configure_cn_mirrors

# ------ Marker helpers ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
step_done() { [[ -f "${MARKER_DIR}/$1.done" ]]; }
mark_done() { date -Iseconds > "${MARKER_DIR}/$1.done"; }

# ------ Step discovery ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
discover_steps() {
    for f in "${STEPS_DIR}"/*.sh; do
        [[ -f "$f" ]] || continue
        echo "$f"
    done | sort
}

# Get step description from the second line (# comment) of a step file.
step_desc() {
    sed -n '2s/^# *//p' "$1"
}

# ------ --reset ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
if [[ "$RESET" == true ]]; then
    rm -f "${MARKER_DIR}"/*.done
    echo "All markers cleared."
    exit 0
fi

# ------ --list ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
if [[ "$LIST_ONLY" == true ]]; then
    while IFS= read -r step_file; do
        step_id="$(basename "$step_file" .sh)"
        if step_done "$step_id"; then
            echo "[done]    $step_id  ($(cat "${MARKER_DIR}/${step_id}.done"))"
        else
            echo "[pending] $step_id  -$(step_desc "$step_file")"
        fi
    done < <(discover_steps)
    exit 0
fi

# ------ Concurrency lock ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------
exec 9>"$LOCK_FILE"
if ! flock -n $LOCK_FD; then
    echo "ERROR: Another setup instance is running (lockfile: $LOCK_FILE)" >&2
    exit 1
fi

# ------ fd redirection ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
# fd 3 = original stdout -backend reads @@SETUP: lines from here
# stdout + stderr -log file (all package manager noise)
LOGFILE="${LOG_DIR}/setup-$(date +%Y%m%d-%H%M%S).log"
exec 3>&1
exec 1>>"$LOGFILE" 2>&1

# ------ Signal handling ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
HEARTBEAT_PID=""

cleanup() {
    [[ -n "$HEARTBEAT_PID" ]] && kill "$HEARTBEAT_PID" 2>/dev/null || true
    flock -u $LOCK_FD 2>/dev/null || true
    rm -f "$LOCK_FILE"
}
trap cleanup EXIT

cancelled() {
    emit _meta error "Cancelled by signal"
    exit 130
}
trap cancelled SIGTERM SIGINT

# ------ Heartbeat ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
start_heartbeat() {
    local step_id="$1"
    (
        while true; do
            sleep 15
            emit "$step_id" heartbeat ""
        done
    ) &
    HEARTBEAT_PID=$!
}

stop_heartbeat() {
    if [[ -n "$HEARTBEAT_PID" ]]; then
        kill "$HEARTBEAT_PID" 2>/dev/null || true
        wait "$HEARTBEAT_PID" 2>/dev/null || true
        HEARTBEAT_PID=""
    fi
}

# ------ Preflight ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
preflight() {
    emit _meta start "Preflight checks"

    # Architecture
    ARCH="$(uname -m)"
    case "$ARCH" in
        x86_64|aarch64) ;;
        *) emit _meta error "Unsupported architecture: $ARCH"; exit 1 ;;
    esac
    export ARCH

    configure_cn_mirrors

    # Disk space (require >= 10 GB free on /)
    local free_kb
    free_kb=$(df / --output=avail | tail -1 | tr -d ' ')
    if (( free_kb < 10485760 )); then
        emit _meta error "Insufficient disk space: $((free_kb / 1024))MB free, need 10GB+"
        exit 1
    fi

    emit _meta done "Preflight OK (arch=$ARCH, free=$((free_kb / 1024))MB)"
}

# ------ run_step ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
run_step() {
    local step_file="$1"
    local step_id
    step_id="$(basename "$step_file" .sh)"

    # Skip if already completed (unless --force)
    if [[ "$FORCE" != true ]] && step_done "$step_id"; then
        emit "$step_id" skip "Already completed ($(cat "${MARKER_DIR}/${step_id}.done"))"
        return 0
    fi

    local desc
    desc="$(step_desc "$step_file")"
    emit "$step_id" start "${desc:-$step_id}"

    start_heartbeat "$step_id"
    local start_ts
    start_ts=$(date +%s)

    # Run step in a subshell so it inherits exported functions + fd 3
    # but cannot kill the orchestrator on failure.
    ( source "$step_file" )
    local rc=$?

    stop_heartbeat

    local elapsed=$(( $(date +%s) - start_ts ))

    if [[ $rc -eq 0 ]]; then
        mark_done "$step_id"
        emit "$step_id" done "Completed in ${elapsed}s"
    else
        emit "$step_id" error "Failed (exit $rc) after ${elapsed}s - see $LOGFILE"
        return $rc
    fi
}

# ------ Main ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
main() {
    preflight

    # Count total steps
    local total=0
    while IFS= read -r _; do
        total=$((total + 1))
    done < <(discover_steps)
    emit _meta progress "total_steps=$total"

    # Single step mode
    if [[ -n "$SINGLE_STEP" ]]; then
        local target="${STEPS_DIR}/${SINGLE_STEP}.sh"
        if [[ ! -f "$target" ]]; then
            emit _meta error "Step not found: $SINGLE_STEP"
            exit 1
        fi
        run_step "$target"
        exit $?
    fi

    # Run all steps in order
    local failed=0
    while IFS= read -r step_file; do
        if ! run_step "$step_file"; then
            failed=1
            break
        fi
    done < <(discover_steps)

    if [[ $failed -gt 0 ]]; then
        emit _meta error "Setup failed - re-run to resume from failed step"
        exit 1
    fi

    emit _meta done "All steps complete"
}

main

