# Install Linux on Xiaomi Mi 8 Lite (platina)

**Development port.** The maintainer's existing installation boots and provides
SSH, but the checked-in integrated Tianma display candidate has not yet passed
its physical boot/power-cycle test. There is no supported prebuilt installer.
Build your own images using [BUILDING.md](BUILDING.md).

These steps are for a **fresh installation** on **Mi 8 Lite / platina**.
Flashing `userdata` destroys Android apps and personal data. For an existing Linux
installation, do not follow the userdata step: keep its filesystem UUID and use
a separately prepared boot/module update with a current backup.

## 1. Prepare recovery and identify the device

- Back up your Android data, the original boot/vbmeta images and the phone-specific
  partitions needed for recovery, using a method you have actually verified.
  Fastboot is not a universal partition-backup tool.
- Retain the matching stock ROM and a working host-side Fastboot recovery path.
  Backups may contain identity/calibration data; keep them private.
- Unlock the bootloader through Xiaomi's supported process before installing Linux.
  Unlocking itself can erase data. This project supplies no bootloader bypass.
- Check the **platina** codename and **Tianma NT36672A** panel variant.
  See [hardware](HARDWARE.md). Do not use the Tianma candidate on an unverified BOE unit.
- Use reliable USB power and a charged, healthy battery. Keep physical access
  throughout the first boot and recovery test.

Enter Fastboot with **Volume Down + Power** from power-off. With only the intended
phone attached, inspect it before any write:

```sh
fastboot devices
fastboot getvar product
fastboot oem device-info
fastboot getvar partition-size:boot
fastboot getvar partition-size:userdata
```

Confirm product `platina`, unlocked status and sufficient partition sizes.
The tested Fastboot boot-image limit was `0x3ffc000` bytes. Recheck your device;
a full raw backup of a partition can exceed the maximum accepted image length.

General device/mode information is also in the
[postmarketOS Mi 8 Lite wiki](https://wiki.postmarketos.org/wiki/Xiaomi_Mi_8_Lite_(xiaomi-platina)).
That page may describe a different kernel/port; use this repository's feature
matrix for this integration's support status.

## 2. Build and verify your own image pair

Follow BUILDING.md through the offline audit and module-index scoping stages.
The examples below assume these files exist:

```sh
ROOTFS=artifacts/candidate-local/xiaomi-platina.img
BOOT=artifacts/candidate-local-scoped/boot.img
make verify DIR=artifacts/candidate-local
make verify DIR=artifacts/candidate-local-scoped
```

The boot command line must refer to the UUID of that root filesystem. Do not mix
a newly generated clean rootfs with a boot prepared for another installation.
All exported modules must match the kernel. Archive your build manifest and APKs.

## 3. Fresh rootfs, vbmeta and RAM boot

**The following commands write to the phone. Run them only after completing the
backup, identification and offline checks.** A RAM boot avoids a permanent kernel
write, but it does not undo a preceding userdata or vbmeta write.

```sh
# Permanently replaces Android user data with your local Linux root filesystem.
fastboot -S 128M flash userdata "$ROOTFS"
# Generates and flashes AVB metadata with verification disabled for this port.
./scripts/pmbootstrap flasher flash_vbmeta
# Test the new kernel/initramfs in RAM before writing the boot partition.
fastboot boot "$BOOT"
```

Stop on any error. Do not flash GPT, bootloader, recovery, persist or modem identity
partitions. Leave the bootloader unlocked. The Fastboot `OKAY` message alone
proves neither that Linux booted nor that the display works.

If USB transfer hangs, investigate the host/cable/Fastboot transport before retrying.
Do not replace a failed RAM test with a blind permanent flash. Never unbind/rebind
MSM DRM on a live system as a substitute for booting the correct device tree.

## 4. Establish SSH and Wi-Fi

The phone's USB gadget address is **172.16.42.1/24**, user **server**. Configure the
host side of the identified USB network interface for **172.16.42.2/24**, without
replacing the host's normal default route. Some desktops do not automatically
choose that address. Use your Linux host's normal network manager and configure
only the interface belonging to this phone.

Verify the phone's SSH host key through a trusted local console or a verified
recovery session before recording it in known_hosts. `ssh-keyscan` by itself does
not authenticate the device. Keep strict host-key checking enabled.

```sh
ssh -i /PATH/TO/YOUR/PRIVATE-KEY -o StrictHostKeyChecking=yes server@172.16.42.1
```

The phone's dedicated administrator has passwordless sudo; password and root SSH
login are disabled. Add your Wi-Fi profile interactively on the phone, so the
passphrase does not become a repository file or shell argument:

```sh
sudo nmcli --ask device wifi connect YOUR_WIFI_SSID
ip -brief address show wlan0
```

Use its DHCP address, or `platina.local` where mDNS works. Test a second SSH
session over Wi-Fi before unplugging USB. USB administration does not by itself
provide Internet access: the host must explicitly share a connection if needed.
No router, firewall, forwarding or VPN changes are made by the build tools.

## 5. Validate, then install the boot image

Verify `uname -r`, the root filesystem, OpenRC services, SSH, Wi-Fi reconnect,
charging/temperature and kernel logs. For the new display candidate, require a
visible correct picture and repeated on/off tests; see [DISPLAY.md](DISPLAY.md).
Retain your stock boot and a way to return to Fastboot throughout.

When the RAM boot is successful, return physically to Fastboot and install the
**same tested** boot image:

```sh
fastboot flash boot "$BOOT"
fastboot reboot
```

Confirm a normal eMMC boot and automatic service startup, then test a separate
charger with Wi-Fi. Test long-term stability and charging under the intended
workload before relying on it as a 24/7 server.

## Recovery and future updates

On a failed candidate, return to Fastboot and restore the verified boot image for
the matching installation and module tree. A stock Android boot alone does not
restore Android userdata that has already been replaced. Follow your stock-ROM
recovery procedure if reverting the whole installation.

For later kernel updates, preserve rootfs UUID, pair kernel/modules/initramfs,
back up the active module tree and configuration, and check any package hooks
before installation. Do not automatically install a new kernel from a rolling
repository. Build, offline audit, RAM test and permanent flash are separate steps.
