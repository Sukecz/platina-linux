# Changelog

## Unreleased — integrated display candidate

- Kernel 7.2.12-r1 adds the Platina Tianma NT36672A panel to the normal driver and device tree.
- Full kernel and module build passed; the existing-installation boot candidate passed offline checks.
- Added display on/off/brightness/status, timed images and host-side image preparation.
- Panel activation, repeated power cycles and power use still require physical testing.

## 0.1.1 — verified integration

- Boot into headless postmarketOS from eMMC with SSH over Wi-Fi or USB networking.
- Key-only SSH, disabled root/password login, NetworkManager reconnect and OpenRC autostart.
- Corrected initramfs module indexes and verified normal restarts.
- Displayed the Platina logo for seven seconds using an explicitly loaded temporary LCD helper.
- Automatic logo and backlight shutdown were physically confirmed on a Tianma Mi 8 Lite.

The integration version is separate from the kernel and distribution versions.
