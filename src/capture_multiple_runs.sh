#!/usr/bin/env bash
# capture_multiple_runs.sh — sequential multi-run bot capture per persona
#
# VERIFIED ARCHITECTURE (2026-07-03):
#   • This script runs on the MAC (dev machine).
#   • The Selenium bot runs LOCALLY on the Mac via `mvn` (real Chrome, Selenium
#     Manager auto-driver). The bot navigates to techmarket.lab, which the Mac's
#     /etc/hosts resolves to the Pi (192.168.10.1) — real traffic over the wire.
#   • tcpdump runs REMOTELY on the Raspberry Pi over SSH, on the Pi's eth0, and
#     captures the Mac<->Pi HTTP traffic. The resulting PCAP is copied back to the
#     Mac and converted to CSV locally with pcap_to_csv.py.
#
#   WHY NOT run the bot on the Pi: the Pi is itself the techmarket.lab server
#   (192.168.10.1 = Pi's own eth0). A bot running ON the Pi would connect to
#   192.168.10.1, which the kernel routes over the LOOPBACK (lo) interface, so
#   `tcpdump -i eth0` would capture nothing real. That is the loopback trap the
#   old version of this script fell into.
#
# Usage:
#   bash capture_multiple_runs.sh [N] [PI_IFACE] [PI_HOST] [CAPTURE_FILTER]
#
#   N              — number of runs per persona (default: 15)
#   PI_IFACE       — capture interface ON THE PI (default: eth0)
#   PI_HOST        — hostname/IP of the Pi (default: 192.168.10.1)
#   CAPTURE_FILTER — tcpdump BPF filter (default: "tcp port 80")
#                    Port-based so it does NOT depend on techmarket.lab resolving
#                    on the Pi (it no longer does) and excludes our SSH (:22).
#
#   The SSH login user defaults to raspberrypie (PI_USER below); the SSH target
#   is PI_USER@PI_HOST.
#
# Examples:
#   bash capture_multiple_runs.sh
#   bash capture_multiple_runs.sh 20
#   bash capture_multiple_runs.sh 2 eth0 192.168.10.1
#   bash capture_multiple_runs.sh 15 eth0 192.168.10.1 "tcp port 80"
#
# Output (in ./captures/):
#   captures/browsing_run1.pcap, captures/browsing_run1.csv, ...
#   captures/browsing.csv      ← merged (all N runs, ready for comparison script)
#   captures/searching.csv
#   captures/formfilling.csv
#
# Requirements:
#   Mac:  Java + Maven, python3 + scapy + cicflowmeter, passwordless SSH to the Pi
#   Pi:   tcpdump installed, passwordless sudo (verified working)

set -euo pipefail

# ── Parameters ────────────────────────────────────────────────────────────────
# Positional order matches the old script (N IFACE HOST) so existing muscle
# memory keeps working; the SSH target is built as PI_USER@PI_HOST.
N="${1:-15}"
PI_IFACE="${2:-eth0}"
PI_HOST="${3:-192.168.10.1}"
CAPTURE_FILTER="${4:-tcp port 80}"
PI_USER="raspberrypie"
PI_SSH="${PI_USER}@${PI_HOST}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOT_DIR="$HOME/Desktop/Docs/traffic-generators/selenium-bot"          # bot runs LOCALLY on the Mac
PCAP_TO_CSV="$SCRIPT_DIR/pcap_to_csv.py"
WORK_DIR="$SCRIPT_DIR/captures"
PERSONAS=("browsing" "searching" "formfilling")

# Remote (Pi) scratch locations
REMOTE_PCAP_DIR="/tmp"
REMOTE_PIDFILE="/tmp/capture_tcpdump.pid"

# ── Sanity checks ─────────────────────────────────────────────────────────────
if [[ ! -f "$PCAP_TO_CSV" ]]; then
    echo "ERROR: pcap_to_csv.py not found at $PCAP_TO_CSV"
    echo "       Place pcap_to_csv.py in the same directory as this script."
    exit 1
fi
if [[ ! -d "$BOT_DIR" ]]; then
    echo "ERROR: Bot directory not found: $BOT_DIR"
    echo "       Set BOT_DIR= in this script if your path differs."
    exit 1
fi
if ! command -v mvn &>/dev/null; then
    echo "ERROR: mvn (Maven) not found on the Mac — the bot runs locally here."
    exit 1
fi
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found."
    exit 1
fi
# Verify SSH + tcpdump + passwordless-sudo-for-tcpdump up front (fail fast).
# NOTE: test with the EXACT privileged command we actually run (tcpdump), not
# `sudo -n true`. The Pi's sudoers grants NOPASSWD only for /usr/bin/tcpdump
# (raspberrypie ALL=(ALL) NOPASSWD: /usr/bin/tcpdump), so `sudo -n true` would
# prompt/fail even though `sudo -n tcpdump` works fine.
if ! ssh -o ConnectTimeout=8 -o BatchMode=yes "$PI_SSH" \
        "command -v tcpdump && sudo -n tcpdump --version" &>/dev/null; then
    echo "ERROR: Cannot reach $PI_SSH with key auth, OR tcpdump / passwordless"
    echo "       sudo-for-tcpdump is unavailable on the Pi."
    echo "       Fix SSH keys / sudoers (NOPASSWD: /usr/bin/tcpdump) / tcpdump first."
    exit 1
fi

mkdir -p "$WORK_DIR"

# ── Global cleanup trap — stops remote tcpdump if the script is interrupted ────
CAPTURE_ACTIVE=0
cleanup() {
    if [[ "$CAPTURE_ACTIVE" -eq 1 ]]; then
        echo ""
        echo "[trap] Stopping remote tcpdump on $PI_SSH ..."
        ssh "$PI_SSH" "sudo sh -c 'kill \$(cat $REMOTE_PIDFILE 2>/dev/null) 2>/dev/null; \
            rm -f $REMOTE_PIDFILE'" 2>/dev/null || true
        CAPTURE_ACTIVE=0
    fi
}
trap cleanup EXIT INT TERM

# ── Helpers ───────────────────────────────────────────────────────────────────
log() { echo "[$(date '+%H:%M:%S')] $*"; }

# Start tcpdump REMOTELY on the Pi. Writes the PCAP under $REMOTE_PCAP_DIR and
# records the tcpdump PID in $REMOTE_PIDFILE so we can stop it precisely.
start_capture() {
    local remote_pcap="$1"
    ssh "$PI_SSH" "rm -f $remote_pcap $REMOTE_PIDFILE; \
        sudo tcpdump -Z raspberrypie -i $PI_IFACE -w $remote_pcap $CAPTURE_FILTER >/dev/null 2>&1 & \
        echo \$! > $REMOTE_PIDFILE"
    CAPTURE_ACTIVE=1
    sleep 1   # let tcpdump initialise and open the capture file
}

# Stop the remote tcpdump and copy the PCAP back to the Mac at $2 (local path).
stop_capture() {
    local remote_pcap="$1"
    local local_pcap="$2"
    ssh "$PI_SSH" "kill \$(cat $REMOTE_PIDFILE 2>/dev/null) 2>/dev/null"
    CAPTURE_ACTIVE=0
    sleep 1   # give tcpdump time to flush and close the file
    if ! scp -q "$PI_SSH:$remote_pcap" "$local_pcap" 2>/dev/null; then
        log "  WARN: scp failed for $remote_pcap (capture may be empty)"
    fi
    ssh "$PI_SSH" "sudo rm -f $remote_pcap $REMOTE_PIDFILE" 2>/dev/null || true
}

# Run the bot LOCALLY on the Mac (real Chrome via Selenium Manager).
run_bot() {
    local persona="$1"
    # cd is scoped to a subshell so it doesn't affect the outer script.
    (cd "$BOT_DIR" && mvn -q exec:java \
        -Dexec.mainClass=com.ids.bot.App \
        -Dexec.args="$persona") \
        && return 0 \
        || { echo "  WARN: mvn exited non-zero (persona=$persona)"; return 0; }
    # Non-zero exit is logged but does NOT abort the loop — a partial session
    # still produces valid flows for statistical analysis.
}

# Inline Python: concatenate per-run CSVs into one merged file for this persona
concat_csvs() {
    local out_csv="$1"
    shift
    local in_csvs=("$@")

    python3 - "$out_csv" "${in_csvs[@]}" <<'PYEOF'
import sys, csv, pathlib

out_path = sys.argv[1]
in_paths = sys.argv[2:]

total = 0
with open(out_path, "w", newline="") as fout:
    writer = None
    for path in in_paths:
        p = pathlib.Path(path)
        if not p.exists() or p.stat().st_size == 0:
            print(f"  skip (empty): {path}")
            continue
        with open(path, newline="") as fin:
            reader = csv.DictReader(fin)
            if not reader.fieldnames:
                print(f"  skip (no header): {path}")
                continue
            if writer is None:
                writer = csv.DictWriter(fout, fieldnames=reader.fieldnames)
                writer.writeheader()
            for row in reader:
                writer.writerow(row)
                total += 1
print(f"  → {total} flows written to {sys.argv[1]}")
PYEOF
}

# ── Main loop ─────────────────────────────────────────────────────────────────
echo "========================================================"
echo "  capture_multiple_runs.sh  (Mac bot + remote Pi tcpdump)"
echo "  N=$N  IFACE=$PI_IFACE  PI=$PI_SSH  FILTER='$CAPTURE_FILTER'"
echo "  Output: $WORK_DIR/"
echo "========================================================"
echo ""

for persona in "${PERSONAS[@]}"; do
    log "=== Persona: $persona ($N runs) ==="
    per_run_csvs=()

    for run in $(seq 1 "$N"); do
        remote_pcap="$REMOTE_PCAP_DIR/${persona}_run${run}.pcap"
        pcap="$WORK_DIR/${persona}_run${run}.pcap"
        csv="$WORK_DIR/${persona}_run${run}.csv"

        log "  [$persona] run $run/$N"

        start_capture "$remote_pcap"         # tcpdump on the Pi
        run_bot "$persona"                   # bot on the Mac
        stop_capture "$remote_pcap" "$pcap"  # stop + pull PCAP to Mac

        # Convert this run's PCAP to CSV (locally on the Mac).
        if [[ -f "$pcap" ]] && [[ -s "$pcap" ]]; then
            python3 "$PCAP_TO_CSV" "$pcap" "$csv"
            per_run_csvs+=("$csv")
        else
            log "  WARN: PCAP missing or empty for run $run — skipping conversion"
        fi

        # Short pause between runs so the server doesn't see back-to-back sessions
        sleep 3
    done

    # Merge all per-run CSVs into one file for this persona
    merged="$WORK_DIR/${persona}.csv"
    log "  Merging ${#per_run_csvs[@]} CSV files → $merged"
    if [[ ${#per_run_csvs[@]} -gt 0 ]]; then
        concat_csvs "$merged" "${per_run_csvs[@]}"
    else
        log "  WARN: No CSV files to merge for $persona"
    fi

    echo ""
done

# ── Summary ───────────────────────────────────────────────────────────────────
echo "========================================================"
echo "  DONE. Merged CSVs:"
for persona in "${PERSONAS[@]}"; do
    f="$WORK_DIR/${persona}.csv"
    if [[ -f "$f" ]]; then
        lines=$(wc -l < "$f")
        flows=$((lines - 1))
        echo "    $f  ($flows flows)"
    else
        echo "    $f  MISSING"
    fi
done
echo ""
echo "  Next step — run the comparison script:"
echo "    python3 $SCRIPT_DIR/zeek_cicids_comparison.py \\"
echo "      --browsing   $WORK_DIR/browsing.csv \\"
echo "      --searching  $WORK_DIR/searching.csv \\"
echo "      --formfilling $WORK_DIR/formfilling.csv \\"
echo "      --server-ip  192.168.10.1 \\"
echo "      --outdir     $SCRIPT_DIR"
echo "========================================================"
