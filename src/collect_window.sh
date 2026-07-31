#!/usr/bin/env bash
# collect_window.sh <window_folder_name>
#
# Run manually AFTER a capture window has finished. Pulls together:
#   1. Zeek logs (conn/http/dns), timestamp-filtered to this window's
#      start_iso/end_iso, from the Pi's own current log dir into the
#      window's zeek/ folder.
#   2. actual_attack_pct computed from the filtered conn.log (attacker-IP
#      flow ratio) and written back into window_meta.json.
#   3. Selenium/Locust ground-truth CSVs from this Mac -> Pi ground_truth/.
#   4. attack_log.csv (+ summary csv if present) from Dell -> Mac tmp -> Pi
#      ground_truth/.
#   5. Marks window_meta.json status as "collected".
#
# --- Fix applied 2026-07-09 ---
# Zeek log collection used to be a plain `sudo cp .../current/$f`, which
# silently grabbed whatever was in the live "current" log at the moment
# this script ran. On the 4-window dry-run this missed almost all of
# window_01/03's traffic: Zeek rotates current/conn.log on the wall-clock
# hour, and collect_window.sh only ever saw the post-rotation sliver, not
# the full window (confirmed: the 2026-07-08 hourly archive for
# window_01's own hour had 68035 rows vs. the 9 rows actually collected).
# Rotation is now disabled on the Pi (one-time manual step, done outside
# this script) so current/conn.log accumulates for the whole multi-window
# run - this script now timestamp-filters it by window_meta.json's
# start_iso/end_iso instead of copying it wholesale, so each window's
# zeek/ folder is correct regardless of rotation state. This also let us
# drop the old `sudo cp` + `chown` dance: conn.log/http.log/dns.log are
# world-readable, and writing the filtered output directly into this
# window's own ids-dataset-raw/.../zeek/ (owned by raspberrypie already)
# needs no sudo at all.
set -euo pipefail

PI_HOST="raspberrypie@192.168.10.1"
DELL_HOST="sshuser@192.168.10.2"
DELL_ATTACK_DIR="C:/attack-lab"
PI_BASE="~/ids-dataset-raw"
PI_ZEEK_CURRENT="/opt/zeek/logs/current"
ATTACKER_IP="192.168.10.2"

# $WINDOW ends up interpolated unquoted into remote ssh command strings below
# (e.g. `> $REMOTE_DIR/zeek/$f`), so it's validated against a strict charset
# (alnum + underscore only, window_<2-digit-seq>_<suffix> shape) instead of
# an exact-name whitelist - this closes command-injection via a crafted
# window name while still accepting any new window without editing this file.
WINDOW_NAME_RE='^window_[0-9]{2}_[A-Za-z0-9]+$'

WINDOW="${1:-}"
if [[ -z "$WINDOW" ]]; then
  echo "Usage: $0 <window_folder_name>" >&2
  echo "Expected format: window_<NN>_<suffix> (e.g. window_12_35target)" >&2
  exit 1
fi

if [[ ! "$WINDOW" =~ $WINDOW_NAME_RE ]]; then
  echo "Unknown/invalid window '$WINDOW'. Expected format: window_<NN>_<suffix> (e.g. window_12_35target)" >&2
  exit 1
fi

REMOTE_DIR="$PI_BASE/$WINDOW"
WINDOW_SUFFIX="${WINDOW#window_??_}"   # e.g. baseline_0pct

# Marks the window as collection_failed on the Pi and aborts. Used whenever
# a step hits a connection/auth/permission error (as opposed to a source
# file that's genuinely absent), since that means the collected data for
# this window can't be trusted as complete.
mark_failed_and_exit() {
  local reason="$1"
  echo "HATA: pencere eksik toplandi. Neden: $reason" >&2
  local mtmp
  mtmp=$(mktemp)
  if scp -q "$PI_HOST:$REMOTE_DIR/window_meta.json" "$mtmp" 2>/dev/null; then
    jq '.status = "collection_failed"' "$mtmp" > "${mtmp}.new"
    scp -q "${mtmp}.new" "$PI_HOST:$REMOTE_DIR/window_meta.json"
  fi
  rm -f "$mtmp" "${mtmp}.new"
  exit 1
}

echo "==> [1/6] window_meta.json start_iso/end_iso okunuyor (zeek ts-filtreleme icin)"
META_TMP=$(mktemp)
scp -q "$PI_HOST:$REMOTE_DIR/window_meta.json" "$META_TMP" || mark_failed_and_exit "window_meta.json indirilemedi"
START_EPOCH=$(python3 -c "
import json, datetime
m = json.load(open('$META_TMP'))
print(datetime.datetime.fromisoformat(m['start_iso'].replace('Z', '+00:00')).timestamp())
")
END_EPOCH=$(python3 -c "
import json, datetime
m = json.load(open('$META_TMP'))
print(datetime.datetime.fromisoformat(m['end_iso'].replace('Z', '+00:00')).timestamp())
")
rm -f "$META_TMP"
echo "    pencere araligi (epoch): $START_EPOCH - $END_EPOCH"

echo "==> [2/6] Zeek loglari (ts-filtreli) Pi uzerinde $REMOTE_DIR/zeek/ icine yaziliyor"
for f in conn.log http.log dns.log; do
  set +e
  out=$(ssh "$PI_HOST" "
    set -e
    src='$PI_ZEEK_CURRENT/$f'
    if [ ! -f \"\$src\" ]; then
      echo '__MISSING__'
      exit 0
    fi
    awk -F'\t' -v start='$START_EPOCH' -v end='$END_EPOCH' '
      /^#/ { print; next }
      { ts = \$1 + 0; if (ts >= start && ts <= end) print }
    ' \"\$src\" > $REMOTE_DIR/zeek/$f
    echo '__OK__'
  " 2>&1)
  rc=$?
  set -e
  if [[ $rc -ne 0 ]]; then
    mark_failed_and_exit "Pi zeek filtreleme hatasi ($f): $out"
  fi
  if [[ "$out" == *"__MISSING__"* ]]; then
    echo "  ($f Pi'de gercekten bulunamadi, atlaniyor)"
    continue
  fi
  if [[ "$out" != *"__OK__"* ]]; then
    mark_failed_and_exit "Pi zeek filtreleme beklenmedik cikti ($f): $out"
  fi
done

echo "==> [3/6] actual_attack_pct hesaplaniyor (saldirgan IP $ATTACKER_IP flow orani, filtrelenmis conn.log uzerinden)"
ATTACK_PCT=$(ssh "$PI_HOST" "
  set -e
  f=$REMOTE_DIR/zeek/conn.log
  if [ ! -s \"\$f\" ]; then
    echo 'null'
    exit 0
  fi
  awk -F'\t' -v atk='$ATTACKER_IP' '
    !/^#/ {
      total++
      if (\$3 == atk || \$5 == atk) attack++
    }
    END {
      if (total == 0) { print \"null\"; exit }
      printf \"%.6f\", (attack / total) * 100
    }
  ' \"\$f\"
")
echo "    actual_attack_pct = $ATTACK_PCT"

META_TMP=$(mktemp)
scp -q "$PI_HOST:$REMOTE_DIR/window_meta.json" "$META_TMP"
if [[ "$ATTACK_PCT" == "null" ]]; then
  jq '.actual_attack_pct = null' "$META_TMP" > "${META_TMP}.new"
else
  jq --argjson v "$ATTACK_PCT" '.actual_attack_pct = $v' "$META_TMP" > "${META_TMP}.new"
fi
scp -q "${META_TMP}.new" "$PI_HOST:$REMOTE_DIR/window_meta.json"
rm -f "$META_TMP" "${META_TMP}.new"

# --- Added 2026-07-10 (see context.md "window_01 kok neden arastirmasi") ---
# window_01_0pct's flow explosion was caused by Zeek being killed/restarted
# mid-capture; the tell-tale sign is a "received termination signal" entry
# in Zeek's own reporter.log with a timestamp inside this window's
# [START_EPOCH, END_EPOCH] range. run_all_windows.sh now also monitors
# Zeek's PID live during the wait (catches it in near-real-time), but this
# is an independent, log-based cross-check that works even for windows
# collected by an older run_all_windows.sh, or if PID monitoring itself
# missed something (e.g. an SSH hiccup during a poll).
echo "==> [4/6] reporter.log kontrol ediliyor (mid-window zeek restart izi var mi)"
# Zeek's /opt/zeek/logs/<date>/ directories are named by the Pi's local
# date (Europe/Istanbul), not UTC - a window can span two local dates near
# midnight, so both the start's and end's local date are checked.
RESTART_HITS=$(ssh "$PI_HOST" "
  set -e
  day_start=\$(TZ=Europe/Istanbul date -d '@$START_EPOCH' +%Y-%m-%d)
  day_end=\$(TZ=Europe/Istanbul date -d '@$END_EPOCH' +%Y-%m-%d)
  days=\"\$day_start\"
  [ \"\$day_end\" != \"\$day_start\" ] && days=\"\$days \$day_end\"
  count=0
  for d in \$days; do
    logdir=/opt/zeek/logs/\"\$d\"
    [ -d \"\$logdir\" ] || continue
    for f in \"\$logdir\"/reporter.*.log.gz; do
      [ -e \"\$f\" ] || continue
      n=\$(zcat \"\$f\" 2>/dev/null | awk -F'\t' -v start='$START_EPOCH' -v end='$END_EPOCH' '
        !/^#/ && \$1+0 >= start && \$1+0 <= end && \$3 ~ /termination signal/ { c++ }
        END { print c+0 }
      ')
      count=\$((count + n))
    done
  done
  echo \"\$count\"
" 2>/dev/null || echo "0")
if [[ "$RESTART_HITS" -gt 0 ]]; then
  echo "    UYARI: pencere araligi icinde $RESTART_HITS adet 'received termination signal' bulundu - zeek muhtemelen pencere ortasinda restart oldu"
  META_TMP=$(mktemp)
  scp -q "$PI_HOST:$REMOTE_DIR/window_meta.json" "$META_TMP"
  jq --argjson n "$RESTART_HITS" \
     '.warning.reporter_termination_signal_in_window = true | .warning.reporter_termination_signal_count = $n' \
     "$META_TMP" > "${META_TMP}.new"
  scp -q "${META_TMP}.new" "$PI_HOST:$REMOTE_DIR/window_meta.json"
  rm -f "$META_TMP" "${META_TMP}.new"
else
  echo "    OK: pencere araliginda zeek restart izi (reporter.log) bulunamadi"
fi

echo "==> [5/6] Copying local ground-truth CSVs (Mac -> Pi)"
scp ~/Desktop/Docs/traffic-generators/selenium-bot/nav_log.csv "$PI_HOST:$REMOTE_DIR/ground_truth/selenium_nav_log.csv"
scp ~/Desktop/Docs/traffic-generators/selenium-bot/session_log.csv "$PI_HOST:$REMOTE_DIR/ground_truth/selenium_session_log.csv"
# locust_ids/nav_log.csv is truncated by run_all_windows.sh right before
# locust starts each window (fix for the append-only cumulative bug), so
# this is already window-specific - no ts-filtering needed here.
scp ~/Desktop/Docs/traffic-generators/locust/locust_ids/nav_log.csv "$PI_HOST:$REMOTE_DIR/ground_truth/locust_nav_log.csv"

# Fetches $1 from Dell into $TMPDIR. Returns 0 if fetched, 1 if genuinely
# missing on Dell (safe to skip). Aborts the whole script via
# mark_failed_and_exit on any connection/auth error, since that means the
# rest of the attack-log data is unverified, not just this one file.
fetch_from_dell() {
  local remote_name="$1" err rc
  set +e
  err=$(scp "$DELL_HOST:$DELL_ATTACK_DIR/$remote_name" "$TMPDIR/" 2>&1 >/dev/null)
  rc=$?
  set -e
  if [[ $rc -eq 0 ]]; then
    return 0
  fi
  if echo "$err" | grep -qiE "no such file|not a regular file"; then
    echo "  ($remote_name Dell'de gercekten bulunamadi, atlaniyor)"
    return 1
  fi
  mark_failed_and_exit "Dell scp hatasi ($remote_name): $err"
}

echo "==> [6/6] Copying attack logs (Dell -> Mac tmp -> Pi), updating status -> collected"
TMPDIR=$(mktemp -d)

# NOTE: attack_log.csv is cumulative on Dell (append-only across all
# windows, by design - see attack_orchestrator.py / run_attack.ps1).
# It's intentionally left unfiltered here; Faz 2 feature extraction is
# expected to filter it by window_meta.json's start_iso/end_iso.
if fetch_from_dell "attack_log.csv"; then
  scp "$TMPDIR/attack_log.csv" "$PI_HOST:$REMOTE_DIR/ground_truth/attack_log.csv"
fi

SUMMARY_NAME="window_${WINDOW_SUFFIX}_summary.csv"
if fetch_from_dell "$SUMMARY_NAME"; then
  scp "$TMPDIR/$SUMMARY_NAME" "$PI_HOST:$REMOTE_DIR/ground_truth/$SUMMARY_NAME"
fi

rm -rf "$TMPDIR"

META_TMP=$(mktemp)
scp -q "$PI_HOST:$REMOTE_DIR/window_meta.json" "$META_TMP"
jq '.status = "collected"' "$META_TMP" > "${META_TMP}.new"
scp -q "${META_TMP}.new" "$PI_HOST:$REMOTE_DIR/window_meta.json"
rm -f "$META_TMP" "${META_TMP}.new"

echo "Done: $WINDOW collected."
