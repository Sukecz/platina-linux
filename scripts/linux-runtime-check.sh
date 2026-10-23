#!/bin/sh
# Read-only runtime inspection after Linux is installed. No package/service changes.
set -u
date -Is
uname -a
cat /etc/os-release
uptime
free -m
df -h
ip address show
ip route
ss -lnt 2>/dev/null || true
rc-status 2>/dev/null || true
printf '\nCPU frequency policies (kHz)\n'
for d in /sys/devices/system/cpu/cpufreq/policy*; do
    [ -d "$d" ] || continue
    for n in scaling_driver scaling_governor scaling_cur_freq scaling_min_freq scaling_max_freq; do
        [ -r "$d/$n" ] && printf '%s: %s\n' "$d/$n" "$(cat "$d/$n")"
    done
done
printf '\nThermal zones (normally millidegrees C)\n'
for d in /sys/class/thermal/thermal_zone*; do
    [ -r "$d/temp" ] || continue
    printf '%s %s: %s\n' "$d" "$(cat "$d/type")" "$(cat "$d/temp")"
done
printf '\nPower supplies: values are driver reports, not wall-power measurements\n'
for d in /sys/class/power_supply/*; do
    [ -d "$d" ] || continue
    for n in type status online capacity temp voltage_now current_now; do
        [ -r "$d/$n" ] && printf '%s: %s\n' "$d/$n" "$(cat "$d/$n")"
    done
done
printf '\nBacklight\n'
for d in /sys/class/backlight/*; do
    [ -d "$d" ] || continue
    for n in brightness actual_brightness max_brightness bl_power; do
        [ -r "$d/$n" ] && printf '%s: %s\n' "$d/$n" "$(cat "$d/$n")"
    done
done
