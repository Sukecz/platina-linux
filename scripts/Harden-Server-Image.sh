#!/bin/sh
# Runs only inside the newly created phone image, never on MiniPC's host OS.
set -eu
test -f /usr/share/deviceinfo/deviceinfo
grep -q xiaomi-platina /usr/share/deviceinfo/deviceinfo
test "$(id -u)" = 0
test -s /home/server/.ssh/authorized_keys
command -v sudo >/dev/null
test -x /usr/sbin/sshd.pam
if ! grep -q '^SSHD_BINARY=' /etc/conf.d/sshd; then
    printf '\nSSHD_BINARY="/usr/sbin/sshd.pam"\n' >> /etc/conf.d/sshd
fi
install -d -m755 /etc/ssh/sshd_config.d /etc/sudoers.d
cat > /etc/ssh/sshd_config.d/00-platina-server.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
UsePAM yes
EOF
if ! grep -q '^Include /etc/ssh/sshd_config.d/' /etc/ssh/sshd_config; then
    sed -i '1i Include /etc/ssh/sshd_config.d/*.conf' /etc/ssh/sshd_config
fi
printf 'server ALL=(ALL) NOPASSWD: ALL\n' > /etc/sudoers.d/90-platina-server
chmod 440 /etc/sudoers.d/90-platina-server
chmod 440 /etc/sudoers
visudo -c
if ! awk -F: '$1 == "server" && substr($2,1,1) == "!" { found=1 } END { exit !found }' /etc/shadow; then
    passwd -l server
fi
chmod 700 /home/server/.ssh
chmod 600 /home/server/.ssh/authorized_keys
chown -R server:server /home/server/.ssh
install -d -m700 -o server -g server /home/server/.config/rc/runlevels/default
test -f /usr/lib/security/pam_rundir.so
cat > /etc/resolv.conf <<'EOF'
nameserver 1.1.1.1
nameserver 1.0.0.1
EOF
cat > /etc/apk/repositories <<'EOF'
https://mirror.nura.eco/postmarketos/v26.06
https://cdn.alpinelinux.org/alpine/v3.24/main
https://cdn.alpinelinux.org/alpine/v3.24/community
EOF
chmod 644 /etc/resolv.conf /etc/apk/repositories
# The versioned runtime overlay supplies the complete display hook and screens.
test -x /etc/local.d/platina-headless.start
test -x /usr/local/libexec/platina-image-runtime
python3 /usr/local/libexec/platina-image-runtime audit
# Hold the exact locally built boot-related packages during normal upgrades.
set --
for package in device-xiaomi-platina firmware-xiaomi-platina linux-postmarketos-qcom-sdm660; do
    version=$(awk -v package="$package" '$0 == "P:" package { found=1; next } found && /^V:/ { print substr($0,3); exit }' /lib/apk/db/installed)
    test -n "$version"
    set -- "$@" "$package=$version"
done
apk add --no-network "$@"
for service in sshd dbus networkmanager usb-moded chronyd local avahi-daemon platina-power-chord; do
    rc-update add "$service" default
done
printf 'Image configured for SSH keys and passwordless sudo for the dedicated administrator.\n'
