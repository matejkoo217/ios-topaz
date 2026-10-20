#!/usr/bin/env bash
# Wait for fuxi in fastboot, then RAM-boot the UniXNU Stage-1 image.
#
# RAM-only: `fastboot boot` does not write any partition. The worst case is the
# device falls back to Android on a cold boot.
#
# Safety:
#   - never flashes, never erases, never touches userdata
#   - refuses to run if more than one fastboot device is attached (no guessing)
#   - refuses if the image hash does not match the recorded one
set -uo pipefail

IMG=/mnt/hdd/Bomb/unixnu-fuxi/build/fuxi/boot/boot.img
WANT_SHA=39ba34dce7bbfc6843f5fd53ebe8f7a91c0921632e8f9661414e4fb8d81a472a
LOG=/mnt/hdd/Bomb/unixnu-fuxi/boot-attempt.log
TIMEOUT_S=${1:-3600}

say() { printf '%s %s\n' "$(date -Is)" "$*" | tee -a "$LOG"; }

say "### watcher start, timeout ${TIMEOUT_S}s"
say "### image: $IMG"

[ -f "$IMG" ] || { say "FATAL image missing"; exit 1; }
GOT_SHA=$(sha256sum "$IMG" | cut -d' ' -f1)
[ "$GOT_SHA" = "$WANT_SHA" ] || { say "FATAL hash mismatch: $GOT_SHA"; exit 1; }
say "### hash ok $GOT_SHA"

deadline=$(( $(date +%s) + TIMEOUT_S ))
while [ "$(date +%s)" -lt "$deadline" ]; do
  mapfile -t devs < <(fastboot devices 2>/dev/null | awk 'NF {print $1}')
  if [ "${#devs[@]}" -gt 1 ]; then
    say "FATAL ${#devs[@]} fastboot devices attached (${devs[*]}); refusing to guess"
    exit 1
  fi
  if [ "${#devs[@]}" -eq 1 ]; then
    say "### detected ${devs[0]}"
    fastboot getvar product 2>&1 | tail -2 | tee -a "$LOG"
    say "### booting (RAM only)"
    timeout 180 fastboot boot "$IMG" 2>&1 | tee -a "$LOG"
    rc=${PIPESTATUS[0]}
    say "### fastboot boot returned rc=$rc"
    # Watch what happens next: a shim that dies leaves the device in the
    # bootloader; a shim that starts hands over and the device may reboot.
    for i in $(seq 1 30); do
      sleep 3
      f=$(fastboot devices 2>/dev/null | awk 'NF {print $1}' | head -1)
      a=$(adb devices 2>/dev/null | awk 'NR>1 && NF {print $1" "$2}' | head -1)
      say "t+$((i*3))s fastboot='${f:-none}' adb='${a:-none}'"
      [ -z "$f" ] && [ -z "$a" ] && say "### device left both fastboot and adb (rebooting or shim running)"
      [ -n "$a" ] && break
    done
    say "### watcher done"
    exit 0
  fi
  sleep 3
done
say "### timeout: no fastboot device in ${TIMEOUT_S}s"
exit 2
