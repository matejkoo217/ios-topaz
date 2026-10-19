#!/usr/bin/env bash
# fuxi-cycle.sh -- one full iteration: put the phone in fastboot, boot an image,
# watch the log, grab a screenshot, and summarise what happened.
#
#   tools/fuxi-cycle.sh build/mt/shim-boot-usbXXX.img [wait_seconds]
#
# Needs root only for the ethertype command channel and for reading the host side
# of the ECM link; the image itself boots with plain fastboot.
set -uo pipefail

IMG=${1:?usage: fuxi-cycle.sh <boot.img> [wait_seconds]}
WAIT=${2:-60}
IFACE=${FUXI_IFACE:-enx02005e77ee01}
LOG=${FUXI_LOG:-/tmp/fuxi/last-boot.txt}
SHOT=${FUXI_SHOT:-/tmp/fuxi/last-screen.png}
SUDO="sudo -S"

mkdir -p "$(dirname "$LOG")" "$(dirname "$SHOT")"

say() { printf '%s\n' "$*"; }

# --- 1. get to fastboot, from wherever the phone is -------------------------
if timeout 5 fastboot devices | grep -q .; then
	say "[1/5] already in fastboot"
elif adb devices | grep -qE "recovery|device$"; then
	say "[1/5] adb present -> rebooting to bootloader"
	adb reboot bootloader >/dev/null 2>&1
	sleep 8
elif timeout 5 fastboot devices | grep -q .; then
	say "[1/5] fastboot after adb"
else
	say "[1/5] FAILED: phone is neither in fastboot nor reachable over adb."
	say "      If XNU is hung it needs a power cycle (hold power ~10 s)."
	exit 2
fi

# --- 2. boot it -------------------------------------------------------------
say "[2/5] booting $IMG"
fastboot boot "$IMG" 2>&1 | tail -2
START=$(date +%s)

# --- 3. capture the console stream while it comes up ------------------------
rm -f "$LOG"
python3 - "$LOG" "$WAIT" <<'PY' &
import socket, sys, time
path, wait = sys.argv[1], float(sys.argv[2])
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("0.0.0.0", 5140))
s.settimeout(1.0)
end = time.time() + wait + 20
with open(path, "ab", buffering=0) as fh:
    while time.time() < end:
        try:
            fh.write(s.recv(4096))
        except socket.timeout:
            pass
PY
CAP=$!

say "[3/5] waiting ${WAIT}s for the link and the boot"
for _ in $(seq 1 "$((WAIT / 2 + 1))"); do
	if ping -c1 -W1 192.168.7.2 >/dev/null 2>&1; then
		say "      link up at $(( $(date +%s) - START ))s"
		break
	fi
	sleep 2
done
sleep "$((WAIT / 2))" 2>/dev/null || true
wait "$CAP" 2>/dev/null

# --- 4. screenshot ----------------------------------------------------------
say "[4/5] screen grab"
printf '%s\n' "${SUDO_PASS:-Vipadni}" | $SUDO python3 "$(dirname "$0")/fuxi-ethcmd.py" "$IFACE" fb >/dev/null 2>&1
if timeout 45 python3 "$(dirname "$0")/fuxi-fb.py" -t 40 -o "$SHOT" 2>&1 | tail -1; then
	:
else
	say "      no frame (link down, or the capture thread refused)"
fi

# --- 5. summary -------------------------------------------------------------
say "[5/5] summary  ($(( $(date +%s) - START ))s total)"
[ -s "$LOG" ] || { say "      NO CONSOLE DATA - phone likely hung or never enumerated"; exit 3; }
printf '      log bytes: %s\n' "$(wc -c < "$LOG")"
for pat in "FUXI USB: ue0" "FUXI CPU: boot epss" "CommCenter" "CRASH " "panic" "FUXI FB:" "LaunchServices\|SpringBoard"; do
	n=$(grep -ac -- "$pat" "$LOG" 2>/dev/null || true)
	[ "${n:-0}" -gt 0 ] && printf '      %-28s %s\n' "$pat" "$n"
done
say "      screen: $SHOT"
