#!/bin/sh
# NetworkManager dispatcher on the phone. No routes or network settings changed.
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH
case "${1:-}:${2:-}" in
    usb0:up|usb0:dhcp4-change|usb0:reapply)
        umask 077
        { date -u '+%Y-%m-%dT%H:%M:%SZ'; /usr/local/sbin/platina-usb-power; } > /run/platina-usb-power-last 2>&1
        ;;
esac
exit 0
