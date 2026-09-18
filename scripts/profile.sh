#!/bin/sh
set -eu
# Usage: scripts/profile.sh PID [seconds]. Observe an already-running board process.
pid=${1:?Provide the board app PID}
seconds=${2:-30}
while [ "$seconds" -gt 0 ] && [ -r "/proc/$pid/status" ]; do
  date -Iseconds
  awk '/VmRSS|VmHWM|Threads/ {print}' "/proc/$pid/status"
  awk '/MemAvailable/ {print}' /proc/meminfo
  ps -p "$pid" -o pid,pcpu,pmem,etime,comm
  sleep 1
  seconds=$((seconds - 1))
done
