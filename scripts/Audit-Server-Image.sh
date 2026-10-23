#!/bin/sh
set -eu
test -f /usr/share/deviceinfo/deviceinfo
grep -q xiaomi-platina /usr/share/deviceinfo/deviceinfo
test -s /home/server/.ssh/authorized_keys
ssh-keygen -lf /home/server/.ssh/authorized_keys
awk -F: '$1 == "server" { if (substr($2,1,1) != "!") exit 1; print "server password locked"; found=1 } END { if (!found) exit 1 }' /etc/shadow
test ! -e /tmp/platina-audit-host-key
ssh-keygen -q -t ed25519 -N '' -f /tmp/platina-audit-host-key
trap 'rm -f /tmp/platina-audit-host-key /tmp/platina-audit-host-key.pub' EXIT
sshd_settings=$(/usr/sbin/sshd.pam -T -h /tmp/platina-audit-host-key)
for expected in 'passwordauthentication no' 'kbdinteractiveauthentication no' 'permitrootlogin no' 'pubkeyauthentication yes' 'usepam yes'; do
    printf '%s\n' "$sshd_settings" | grep -Fx "$expected"
done
grep -q '^SSHD_BINARY="/usr/sbin/sshd.pam"' /etc/conf.d/sshd
visudo -c
test -f /usr/lib/security/pam_rundir.so
test -x /usr/sbin/avahi-daemon
test -x /usr/sbin/NetworkManager
test -x /usr/sbin/usb_moded
test -x /usr/sbin/chronyd
test -d /home/server/.config/rc/runlevels/default
test -s /etc/NetworkManager/system-connections/platina-usb.nmconnection
test "$(stat -c '%a:%u:%g' /etc/NetworkManager/system-connections/platina-usb.nmconnection)" = '600:0:0'
test -z "$(find /etc/NetworkManager/system-connections -type f -name '*.nmconnection' ! -name platina-usb.nmconnection -print)"
test -z "$(find /home -type f -name 'id_*' -print)"
grep -q '^wifi.scan-rand-mac-address=no$' /etc/NetworkManager/conf.d/30-platina-wifi.conf
grep -q '^nameserver 1.1.1.1$' /etc/resolv.conf
grep -q '^https://mirror.nura.eco/postmarketos/v26.06$' /etc/apk/repositories
for package in device-xiaomi-platina firmware-xiaomi-platina linux-postmarketos-qcom-sdm660; do
    grep -q "^$package=" /etc/apk/world
done
python3 /usr/local/libexec/platina-image-runtime audit
for service in sshd dbus networkmanager usb-moded chronyd local avahi-daemon platina-power-chord; do
    test -L "/etc/runlevels/default/$service"
done
for key in /etc/ssh/ssh_host_*_key; do
    if [ -f "$key" ]; then
        echo 'Build-time SSH host key found; needs removal before final export.'
        exit 1
    fi
done
echo 'Offline image audit passed; runtime networking and boot still need testing.'
