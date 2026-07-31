#!/usr/bin/env bash
# run_all_windows.sh
#
# Full N-window IDS dataset capture orchestration, run from this Mac.
# For each window: starts Selenium + Locust (benign traffic) locally,
# triggers attack_orchestrator.py on Dell if target_pct>0, waits for the
# window duration + safety margin, verifies processes actually stopped,
# runs collect_window.sh, and moves to the next window.
#
# A collection_failed window does NOT stop the run - it's logged and we
# move on. Everything is timestamped into master_log.txt.
#
# --- Fixes applied 2026-07-09 (see IDS-Analysis/context.md for the full
#     writeup of the 4-window dry-run findings that motivated these) ---
# 1. Zeek capture health-check + retry: the root cause of window_01/03's
#    missing flows was NOT a zeek restart race, it was hourly wall-clock
#    log rotation on the Pi (confirmed: 68035 rows sat in the
#    2026-07-08/conn.17:00:00-18:00:00.log.gz archive that collect_window.sh
#    never touched). Rotation itself is disabled on the Pi separately
#    (one-time manual step, see the instructions handed to the user
#    alongside this script) and collect_window.sh now timestamp-filters
#    the (now effectively cumulative) current/conn.log instead of just
#    copying it verbatim. The health-check below is a SEPARATE safety net
#    for genuine capture-down scenarios (interface down, zeek crashed) -
#    it does not by itself fix the rotation bug.
# 2. Locust's nav_log.csv is append-only (request_logger.py opens it in
#    "a" mode and only writes a header if the file is new/empty) - it was
#    accumulating across all 4 windows. It's now truncated right before
#    locust starts each window, matching Selenium's NavLog.java behavior
#    (TRUNCATE_EXISTING on JVM start).
# 3. window_meta.json's start_iso/end_iso used to be produced by
#    `date -u +%Y-%m-%dT%H:%M:%S.%3NZ`, but macOS's BSD `date` doesn't
#    support %N - it was passed through literally, producing invalid
#    ISO8601 like "...T16:39:21.3NZ". Timestamps are now generated with
#    python3 for portable, correct millisecond precision.
# 4. actual_attack_pct is now computed by collect_window.sh from the
#    filtered conn.log (attacker-IP flow ratio) and written back into
#    window_meta.json - it used to be left as `null` forever.
# 5. Window length is now 60 minutes total (50 min active traffic
#    generation + 10 min safety margin, preserving the original 75/90
#    "active/total" ratio). attack_orchestrator.py's BENIGN_FLOWS_PER_75MIN
#    constant already scales proportionally via
#    `BENIGN_FLOWS_PER_75MIN * (window_minutes/75.0)`, so no Dell-side
#    code change was needed - only WINDOW_MINUTES here changed.
set -uo pipefail   # NOT -e: a failure in one window must not kill the whole run

PI_HOST="raspberrypie@192.168.10.1"
DELL_HOST="sshuser@192.168.10.2"
DELL_PYTHON="C:/Program Files/Python313/python.exe"
DELL_ORCHESTRATOR="C:/attack-lab/attack_orchestrator.py"
PI_BASE="~/ids-dataset-raw"
PI_ZEEK_CURRENT="/opt/zeek/logs/current"

SELENIUM_DIR=~/Desktop/Docs/traffic-generators/selenium-bot
LOCUST_DIR=~/Desktop/Docs/traffic-generators/locust
COLLECT_SCRIPT=~/Desktop/Docs/scripts/collect_window.sh
RUN_LOG_DIR=~/Desktop/Docs/logs/window_run_logs_data
MASTER_LOG=~/Desktop/Docs/logs/master_log_data.txt

# 60-min window = 50min active traffic generation + 10min safety margin/drain
# (0.833 active/total ratio, same as the original 75/90 design).
# Override via env for a quick dry-run, e.g.:
#   WINDOW_MINUTES=4 SAFETY_MARGIN_MINUTES=1 ./run_all_windows.sh
WINDOW_MINUTES="${WINDOW_MINUTES:-50}"
SAFETY_MARGIN_MINUTES="${SAFETY_MARGIN_MINUTES:-10}"
BREATHING_GAP_SECONDS=120
DELL_CHECK_AND_KILL="C:/attack-lab/check_and_kill.ps1"

ZEEK_HEALTHCHECK_TIMEOUT_S=30
ZEEK_HEALTHCHECK_INTERVAL_S=5
MAX_WINDOW_RETRIES=2

# --- Mid-window Zeek restart monitor (added 2026-07-10, see context.md
# "window_01 kok neden arastirmasi") - window_01_0pct's flow explosion
# (329K flows, 96.8% OTH state) traced back to Zeek being killed and
# restarted mid-capture (3x within 25s, ~7min into the window). The
# startup health-check above only observes the first 30s, so a restart
# happening later in the window went undetected until Faz 2 archaeology.
# This polls Zeek's PID throughout the full wait period instead.
ZEEK_PID_CHECK_INTERVAL_S=150

mkdir -p "$RUN_LOG_DIR"

# window_folder_name : target_pct
# 9-point contamination series (0/3/5/7/12/15/17/22/30%), ascending. Naming
# dropped the baseline/train_b/train_c/test labels (window_NN_<pct>pct only)
# since with 9 points a descriptive label per window stopped being meaningful.
WINDOWS=(
  "window_02_3pct:3"
  "window_03_5pct:5"
  "window_04_7pct:7"
  "window_05_12pct:12"
  "window_06_15pct:15"
  "window_07_17pct:17"
  "window_09_20pct:20"
  "window_08_22pct:22"
  "window_12_35target:35"
  "window_13_60target:60"
)

# Optional positional args: one or more window names (e.g.
#   ./run_all_windows.sh window_09_20pct window_06_15pct
# ) to run only those windows, in their WINDOWS-array order (not argv order)
# so the ascending-contamination safety assumptions elsewhere in the script
# still hold. No args = run the full WINDOWS array (old behavior).
if [[ "$#" -gt 0 ]]; then
  SELECTED_NAMES=("$@")
  FILTERED_WINDOWS=()
  for entry in "${WINDOWS[@]}"; do
    entry_name="${entry%%:*}"
    for wanted in "${SELECTED_NAMES[@]}"; do
      if [[ "$entry_name" == "$wanted" ]]; then
        FILTERED_WINDOWS+=("$entry")
        break
      fi
    done
  done
  for wanted in "${SELECTED_NAMES[@]}"; do
    found=0
    for entry in "${WINDOWS[@]}"; do
      [[ "${entry%%:*}" == "$wanted" ]] && found=1 && break
    done
    if [[ "$found" -eq 0 ]]; then
      echo "HATA: bilinmeyen window adi: $wanted (WINDOWS dizisinde yok)" >&2
      exit 1
    fi
  done
  WINDOWS=("${FILTERED_WINDOWS[@]}")
fi

# --- portable UTC ISO8601 with millisecond precision (BSD `date` has no %N) ---
now_iso() {
  python3 -c '
import datetime
n = datetime.datetime.now(datetime.timezone.utc)
print(n.strftime("%Y-%m-%dT%H:%M:%S.") + f"{n.microsecond // 1000:03d}Z")
'
}

log() {
  echo "[$(now_iso)] $*" | tee -a "$MASTER_LOG"
}

# Pulls window_meta.json down, sets one field via jq, pushes it back.
# $2 is a JSON-encoded value, e.g. '"running"' for a string or 0 for a number.
update_meta_field() {
  local window="$1" field="$2" json_value="$3"
  local remote_dir="$PI_BASE/$window"
  local mtmp
  mtmp=$(mktemp)
  if ! scp -q "$PI_HOST:$remote_dir/window_meta.json" "$mtmp" 2>/dev/null; then
    log "  UYARI: $window/window_meta.json indirilemedi, $field guncellenemedi"
    rm -f "$mtmp"
    return 1
  fi
  jq ".$field = $json_value" "$mtmp" > "${mtmp}.new"
  scp -q "${mtmp}.new" "$PI_HOST:$remote_dir/window_meta.json"
  rm -f "$mtmp" "${mtmp}.new"
}

# Confirms /opt/zeek/logs/current/conn.log's row count is actually
# increasing over ZEEK_HEALTHCHECK_TIMEOUT_S. This is a liveness check on
# the capture process, run WHILE Selenium/Locust/Dell traffic is already
# flowing (checking before any traffic exists would have no signal to
# observe) - it does not validate the hourly-rotation fix, which is
# handled separately (rotation disabled on the Pi + timestamp filtering
# in collect_window.sh).
zeek_health_check() {
  local window="$1"
  local remote_conn="$PI_ZEEK_CURRENT/conn.log"
  local elapsed=0 prev count
  prev=$(ssh "$PI_HOST" "wc -l < '$remote_conn' 2>/dev/null")
  [[ -z "$prev" ]] && prev=0
  while [[ "$elapsed" -lt "$ZEEK_HEALTHCHECK_TIMEOUT_S" ]]; do
    sleep "$ZEEK_HEALTHCHECK_INTERVAL_S"
    elapsed=$((elapsed + ZEEK_HEALTHCHECK_INTERVAL_S))
    count=$(ssh "$PI_HOST" "wc -l < '$remote_conn' 2>/dev/null")
    [[ -z "$count" ]] && count=0
    if [[ "$count" -gt "$prev" ]]; then
      log "[$window]     zeek health-check OK: conn.log $prev -> $count satir (${elapsed}sn icinde buyudu)"
      return 0
    fi
    prev=$count
  done
  log "[$window]     zeek health-check FAILED: conn.log ${ZEEK_HEALTHCHECK_TIMEOUT_S}sn icinde buyumedi (son sayim: $count)"
  return 1
}

# Returns zeekctl's own idea of the current Zeek PID (the "Pid" column of
# `zeekctl status`), which is the authoritative source zeekctl itself
# restarts/tracks - more reliable than pgrep, which can transiently match
# unrelated short-lived processes with "eth0" in their command line.
# Empty output means zeekctl status itself failed (SSH/connectivity issue,
# not necessarily zeek being down) - callers must treat that as "unknown",
# not as a restart.
get_zeek_pid() {
  ssh "$PI_HOST" "/opt/zeek/bin/zeekctl status 2>/dev/null | awk '\$1==\"zeek\" {print \$5}'" 2>/dev/null
}

# Sleeps for $2 (total_seconds), polling Zeek's PID every
# ZEEK_PID_CHECK_INTERVAL_S against the PID it started with ($3). If the
# PID changes mid-wait, logs it immediately and writes
# warning.mid_window_zeek_restart=true (+ the detection timestamp) into
# window_meta.json on the Pi - the window is NOT aborted (traffic
# generation on the Mac/Dell side is independent of this), just flagged
# for Faz 2 to treat with suspicion, same as window_01 should have been.
wait_with_zeek_monitor() {
  local window="$1" total_seconds="$2" start_pid="$3"
  local elapsed=0 chunk cur_pid restart_flagged=0

  while [[ "$elapsed" -lt "$total_seconds" ]]; do
    chunk="$ZEEK_PID_CHECK_INTERVAL_S"
    if [[ $((elapsed + chunk)) -gt "$total_seconds" ]]; then
      chunk=$((total_seconds - elapsed))
    fi
    sleep "$chunk"
    elapsed=$((elapsed + chunk))

    cur_pid=$(get_zeek_pid)
    if [[ -z "$cur_pid" ]]; then
      log "[$window]     zeek PID izleme: durum okunamadi (SSH/zeekctl hatasi olabilir), bu tur atlaniyor"
      continue
    fi
    if [[ "$cur_pid" != "$start_pid" ]]; then
      log "[$window]     UYARI: mid-window zeek restart tespit edildi! baslangic PID=$start_pid, simdiki PID=$cur_pid (t=${elapsed}sn)"
      restart_flagged=1
      start_pid="$cur_pid"   # keep tracking from the new PID, further restarts also get logged
    fi
  done

  if [[ "$restart_flagged" -eq 1 ]]; then
    log "[$window]     mid-window zeek restart(lari) window_meta.json'a warning olarak yaziliyor"
    # .warning.<field> = ... (not .warning = {...}) so this merges into any
    # existing warning object instead of clobbering fields collect_window.sh
    # may set later (e.g. reporter_termination_signal_in_window).
    update_meta_field "$window" "warning.mid_window_zeek_restart" 'true'
    update_meta_field "$window" "warning.mid_window_zeek_restart_detected_at" "\"$(now_iso)\""
  fi
}

# Starts Selenium/Locust/Dell for $1 (window) at $2 (target_pct), logging
# into $3 (win_log_dir). Sets SELENIUM_PID / LOCUST_PID / DELL_PID globals.
start_window_traffic() {
  local window="$1" target_pct="$2" win_log_dir="$3"

  log "[$window] [1] Selenium MixedTrafficRunner baslatiliyor (arka plan, ${WINDOW_MINUTES}dk)"
  ( cd "$SELENIUM_DIR" && nohup mvn exec:java \
      -Dexec.mainClass=com.ids.bot.MixedTrafficRunner \
      -Dexec.args="$WINDOW_MINUTES" \
      > "$win_log_dir/selenium.log" 2>&1 & echo $! > "$win_log_dir/selenium.pid" )
  SELENIUM_PID=$(cat "$win_log_dir/selenium.pid")
  log "[$window]     selenium pid=$SELENIUM_PID, log=$win_log_dir/selenium.log"

  log "[$window] [2] Locust nav_log.csv sifirlaniyor (append-only - onceki pencerenin verisi kalmasin)"
  : > "$LOCUST_DIR/locust_ids/nav_log.csv"

  log "[$window] [2] Locust baslatiliyor (arka plan, ${WINDOW_MINUTES}dk)"
  ( cd "$LOCUST_DIR" && nohup locust --headless -u 30 -r 30 \
      --run-time "${WINDOW_MINUTES}m" --stop-timeout 90 \
      > "$win_log_dir/locust.log" 2>&1 & echo $! > "$win_log_dir/locust.pid" )
  LOCUST_PID=$(cat "$win_log_dir/locust.pid")
  log "[$window]     locust pid=$LOCUST_PID, log=$win_log_dir/locust.log"

  DELL_PID=""
  if [[ "$target_pct" -gt 0 ]]; then
    local window_suffix="${window#window_??_}"
    log "[$window] [3] Dell attack_orchestrator.py tetikleniyor (target_pct=$target_pct)"
    ( ssh "$DELL_HOST" "\"$DELL_PYTHON\" \"$DELL_ORCHESTRATOR\" --window-minutes $WINDOW_MINUTES --target-pct $target_pct --window-label $window_suffix" \
        > "$win_log_dir/dell_orchestrator.log" 2>&1 & echo $! > "$win_log_dir/dell.pid" )
    DELL_PID=$(cat "$win_log_dir/dell.pid")
    log "[$window]     dell orchestrator (local ssh) pid=$DELL_PID, log=$win_log_dir/dell_orchestrator.log"
  else
    log "[$window] [3] target_pct=0, Dell'de saldiri tetiklenmiyor"
  fi
}

# Checks $1's (window) folder doesn't already exist on the Pi - a conflict
# there means either a leftover from a previous run or a naming collision,
# and we'd rather stop and let a human look than silently overwrite
# already-collected data. If clear, creates the folder structure + an
# initial window_meta.json (status="pending") for $2 (target_pct). No
# separate manual init step is needed anymore - this script is now
# self-contained for a completely fresh ids-dataset-raw/.
ensure_window_dir() {
  local window="$1" target_pct="$2"
  local remote_dir="$PI_BASE/$window"
  local exists
  exists=$(ssh "$PI_HOST" "[ -d $remote_dir ] && echo EXISTS || echo MISSING")
  if [[ "$exists" == "EXISTS" ]]; then
    log "[$window] HATA: $remote_dir Pi'de zaten mevcut - cakisma riski var, script DURDURULUYOR."
    log "[$window] Bu, eski/yarim kalmis bir veri ya da isimlendirme cakismasi olabilir - elle inceleyip"
    log "[$window] gerekiyorsa temizledikten sonra script'i tekrar calistir. (Uzerine sessizce yazilmadi.)"
    return 1
  fi
  log "[$window] Pi'de pencere klasoru + baslangic window_meta.json olusturuluyor ($remote_dir)"
  ssh "$PI_HOST" "mkdir -p $remote_dir/zeek $remote_dir/ground_truth"
  local init_meta
  init_meta=$(mktemp)
  cat > "$init_meta" << EOF
{
  "window_label": "$window",
  "target_pct": $target_pct,
  "start_iso": null,
  "end_iso": null,
  "actual_attack_pct": null,
  "status": "pending"
}
EOF
  scp -q "$init_meta" "$PI_HOST:$remote_dir/window_meta.json"
  rm -f "$init_meta"
  return 0
}

# Kills whatever start_window_traffic just started, for a failed-healthcheck retry.
stop_window_traffic() {
  local window="$1"
  log "[$window]     saglik kontrolu basarisiz - bu denemenin surecleri durduruluyor"
  [[ -n "${SELENIUM_PID:-}" ]] && kill -9 "$SELENIUM_PID" 2>/dev/null
  [[ -n "${LOCUST_PID:-}" ]] && kill -9 "$LOCUST_PID" 2>/dev/null
  if [[ -n "${DELL_PID:-}" ]]; then
    ssh "$DELL_HOST" "powershell -NoProfile -ExecutionPolicy Bypass -File $DELL_CHECK_AND_KILL" >/dev/null 2>&1
    kill -9 "$DELL_PID" 2>/dev/null
  fi
}

for entry in "${WINDOWS[@]}"; do
  WINDOW="${entry%%:*}"
  TARGET_PCT="${entry##*:}"
  WINDOW_SUFFIX="${WINDOW#window_??_}"
  WIN_LOG_DIR="$RUN_LOG_DIR/$WINDOW"
  mkdir -p "$WIN_LOG_DIR"

  log "==================== $WINDOW (target_pct=$TARGET_PCT) BASLIYOR ===================="

  if ! ensure_window_dir "$WINDOW" "$TARGET_PCT"; then
    log "TUM KOSU DURDURULUYOR ($WINDOW icin klasor cakismasi)."
    exit 1
  fi

  # --- steps 1-3 + health-check, with retry on a dead/hung capture ---
  attempt=1
  healthy=0
  while [[ "$attempt" -le "$MAX_WINDOW_RETRIES" ]]; do
    log "[$WINDOW] deneme $attempt/$MAX_WINDOW_RETRIES"
    start_window_traffic "$WINDOW" "$TARGET_PCT" "$WIN_LOG_DIR"
    log "[$WINDOW] [3.5] zeek capture health-check calisiyor (max ${ZEEK_HEALTHCHECK_TIMEOUT_S}sn)"
    if zeek_health_check "$WINDOW"; then
      healthy=1
      break
    fi
    stop_window_traffic "$WINDOW"
    attempt=$((attempt + 1))
    if [[ "$attempt" -le "$MAX_WINDOW_RETRIES" ]]; then
      log "[$WINDOW]     ${BREATHING_GAP_SECONDS}sn bekleyip yeniden denenecek"
      sleep "$BREATHING_GAP_SECONDS"
    fi
  done

  if [[ "$healthy" -ne 1 ]]; then
    log "[$WINDOW]     HATA: zeek capture $MAX_WINDOW_RETRIES denemede de saglikli baslamadi - pencere ATLANIYOR, status=collection_failed"
    update_meta_field "$WINDOW" "status" '"collection_failed"'
    update_meta_field "$WINDOW" "failure_reason" '"zeek_capture_healthcheck_failed"'
    log "==================== $WINDOW ATLANDI ===================="
    log "Sonraki pencereden once ${BREATHING_GAP_SECONDS}sn nefes payi bekleniyor..."
    sleep "$BREATHING_GAP_SECONDS"
    continue
  fi

  # --- step 4: mark window running ---
  START_ISO=$(now_iso)
  log "[$WINDOW] [4] window_meta.json guncelleniyor: start_iso=$START_ISO, status=running"
  update_meta_field "$WINDOW" "start_iso" "\"$START_ISO\""
  update_meta_field "$WINDOW" "status" '"running"'

  ZEEK_START_PID=$(get_zeek_pid)
  if [[ -z "$ZEEK_START_PID" ]]; then
    log "[$WINDOW]     UYARI: pencere baslangicinda zeek PID'i okunamadi - mid-window restart izleme bu pencerede calismayacak"
  else
    log "[$WINDOW]     zeek PID izleme baslatiliyor (baslangic PID=$ZEEK_START_PID, her ${ZEEK_PID_CHECK_INTERVAL_S}sn kontrol)"
  fi

  # --- step 5: wait window_minutes + safety margin, monitoring zeek's PID
  # throughout (not just at start) so a mid-window restart like window_01's
  # gets caught instead of silently corrupting the whole rest of the window ---
  TOTAL_WAIT_S=$(( (WINDOW_MINUTES + SAFETY_MARGIN_MINUTES) * 60 ))
  log "[$WINDOW] [5] ${TOTAL_WAIT_S}sn (${WINDOW_MINUTES}+${SAFETY_MARGIN_MINUTES}dk) bekleniyor..."
  if [[ -n "$ZEEK_START_PID" ]]; then
    wait_with_zeek_monitor "$WINDOW" "$TOTAL_WAIT_S" "$ZEEK_START_PID"
  else
    sleep "$TOTAL_WAIT_S"
  fi

  # --- step 6: verify processes actually stopped, force-kill stragglers ---
  log "[$WINDOW] [6] surecler kontrol ediliyor"
  if kill -0 "$SELENIUM_PID" 2>/dev/null; then
    log "[$WINDOW]     UYARI: selenium (pid=$SELENIUM_PID) hala calisiyor, zorla durduruluyor"
    kill -9 "$SELENIUM_PID" 2>/dev/null
  else
    log "[$WINDOW]     selenium bitti (pid=$SELENIUM_PID)"
  fi
  if kill -0 "$LOCUST_PID" 2>/dev/null; then
    log "[$WINDOW]     UYARI: locust (pid=$LOCUST_PID) hala calisiyor, zorla durduruluyor"
    kill -9 "$LOCUST_PID" 2>/dev/null
  else
    log "[$WINDOW]     locust bitti (pid=$LOCUST_PID)"
  fi
  if [[ -n "$DELL_PID" ]]; then
    # Dosya-tabanli dogrulama once: Dell'de python(attack_orchestrator.py)/slowloris
    # hala calisiyorsa Windows tarafinda bizzat Stop-Process ile kapat - sadece
    # yerel ssh kanalini kesmek uzak sureci her zaman durdurmayabilir.
    CHECK_OUT=$(ssh "$DELL_HOST" "powershell -NoProfile -ExecutionPolicy Bypass -File $DELL_CHECK_AND_KILL" 2>&1)
    log "[$WINDOW]     dell check_and_kill.ps1 sonucu: $CHECK_OUT"
    if kill -0 "$DELL_PID" 2>/dev/null; then
      log "[$WINDOW]     UYARI: dell orchestrator (pid=$DELL_PID) ssh kanali hala acik, kapatiliyor"
      kill -9 "$DELL_PID" 2>/dev/null
    else
      log "[$WINDOW]     dell orchestrator bitti (pid=$DELL_PID)"
    fi
  fi

  # --- step 7: mark end_iso BEFORE collecting - collect_window.sh now needs
  # both start_iso and end_iso to timestamp-filter the zeek/Locust logs, so
  # this must be written first (the old script only needed end_iso for
  # record-keeping, so it used to run after collection - that ordering
  # broke collect_window.sh's new ts-filter step, caught by the dry-run).
  END_ISO=$(now_iso)
  log "[$WINDOW] [7] window_meta.json guncelleniyor: end_iso=$END_ISO"
  update_meta_field "$WINDOW" "end_iso" "\"$END_ISO\""

  # --- step 8: collect ---
  log "[$WINDOW]     not: Dell'deki attack_log.csv kumulatif (pencere basina sifirlanmiyor, bilincli tasarim) -"
  log "[$WINDOW]     Faz 2'de window_meta.json start_iso/end_iso ile zaman damgasina gore filtrelenecek."
  log "[$WINDOW]     Zeek current/conn.log de artik kumulatif olabilir (rotasyon Pi'de kapatildiysa) -"
  log "[$WINDOW]     collect_window.sh bunu artik ayni sekilde start_iso/end_iso'ya gore filtreliyor."
  # 5sn bekleniyor: dry-run'da bulundu - end_iso yazildiktan hemen sonra
  # collect_window.sh calisirsa, Zeek'in log buffer'i pencerenin son birkac
  # saniyesindeki bazi flow'lari henuz diske flush etmemis olabiliyor
  # (gozlemlenen: ~%1.9 eksik satir). Bu bekleme, ts-filtrelemenin gercekten
  # tam olmasini garantiliyor.
  sleep 5
  log "[$WINDOW] [8] collect_window.sh calistiriliyor"
  if bash "$COLLECT_SCRIPT" "$WINDOW" >> "$WIN_LOG_DIR/collect.log" 2>&1; then
    log "[$WINDOW]     collect_window.sh basarili (log: $WIN_LOG_DIR/collect.log)"
  else
    log "[$WINDOW]     HATA: collect_window.sh basarisiz oldu (collection_failed) - $WINDOW ATLANIYOR, sonraki pencereye geciliyor (log: $WIN_LOG_DIR/collect.log)"
  fi

  log "==================== $WINDOW TAMAMLANDI ===================="

  # --- step 9: breathing gap before next window ---
  log "Sonraki pencereden once ${BREATHING_GAP_SECONDS}sn nefes payi bekleniyor..."
  sleep "$BREATHING_GAP_SECONDS"
done

log "TUM PENCERELER TAMAMLANDI."
