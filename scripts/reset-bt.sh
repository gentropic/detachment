#!/usr/bin/env bash
# Clear detachment's Bluetooth state on jt when Windows won't pair/reconnect ("can't connect").
# Removes all bonds + restarts bluetoothd, so you can pair fresh. Run:  sudo ./reset-bt.sh
#
# Then:  sudo ./run-daemon.sh   (it flips pairable on + registers the agent/SDP)
#        on Windows: remove "detachment" from Bluetooth settings, then Add device again.
set -e
if [ "$(id -u)" -ne 0 ]; then exec sudo "$0" "$@"; fi

for m in $(bluetoothctl devices Paired 2>/dev/null | awk '{print $2}'); do
  bluetoothctl remove "$m" >/dev/null 2>&1 && echo "removed bond $m"
done
systemctl restart bluetooth
sleep 2
echo "BT reset. Start the daemon, then remove+re-add 'detachment' on Windows."
