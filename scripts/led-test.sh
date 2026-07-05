#!/usr/bin/env bash
# detachment LED experiment — find which keyboard LED actually lights the physical key, and check
# whether writes stick (GNOME/keyd can fight us). Run as root:  sudo ./led-test.sh <cmd> [filter]
#
#   sudo ./led-test.sh list                 # every LED + its current/max brightness
#   sudo ./led-test.sh blink [capslock]     # blink each matching LED in turn — WATCH your keyboard
#   sudo ./led-test.sh on   [capslock]      # force matching LEDs on   (see if it sticks)
#   sudo ./led-test.sh off  [capslock]      # force matching LEDs off
#   sudo ./led-test.sh stick <name>         # set one LED on, re-read for 5s (does GNOME clobber it?)
#
# filter is a substring of the LED name, default "capslock". Try numlock/scrolllock too.
set -u
cmd="${1:-blink}"
filter="${2:-capslock}"
match() { ls -d /sys/class/leds/*"$filter"* 2>/dev/null; }

case "$cmd" in
  list)
    for l in /sys/class/leds/*/; do
      n=$(basename "$l")
      printf '%-32s %s/%s\n' "$n" "$(cat "$l/brightness" 2>/dev/null)" "$(cat "$l/max_brightness" 2>/dev/null)"
    done ;;

  on|off)
    v=$([ "$cmd" = on ] && echo 1 || echo 0)
    for l in $(match); do echo "$v -> $(basename "$l")"; echo "$v" > "$l/brightness"; done ;;

  blink)
    found=$(match)
    [ -z "$found" ] && { echo "no LEDs match '*$filter*'"; exit 1; }
    for l in $found; do
      echo "--- blinking $(basename "$l") — is a key lighting up? ---"
      for _ in 1 2 3 4 5 6; do echo 1 > "$l/brightness"; sleep 0.4; echo 0 > "$l/brightness"; sleep 0.3; done
    done
    echo "done." ;;

  stick)
    l="/sys/class/leds/$filter"
    [ -e "$l/brightness" ] || { echo "no such LED: $filter (use the full name from 'list')"; exit 1; }
    echo 1 > "$l/brightness"
    echo -n "set 1; re-reading for 5s: "
    for _ in $(seq 1 10); do printf '%s' "$(cat "$l/brightness")"; sleep 0.5; done
    echo "  (all 1 = ours; drops to 0 = something clobbers it)"
    echo 0 > "$l/brightness" ;;

  *) echo "usage: $0 [list|blink|on|off|stick] [filter]"; exit 1 ;;
esac
