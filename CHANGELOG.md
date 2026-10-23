# Changelog

## 0.3.1 — fresh-image integration

- New local images include versioned boot and shutdown screens, display helpers,
  the headless boot hook and the enabled OpenRC shutdown-button service.
- Image audits verify decoded screens, file hashes, permissions and service links.
- Exported boot images automatically receive module indexes matching the actual
  initramfs contents; the final boot/rootfs pair is audited before build success.
- A full local image passed offline audits. The existing installation was updated
  in place to 0.3.1: screen preview, normal restart, runtime checksums, SSH and
  service autostart passed. The new full installation image was not flashed.

## 0.3.0 — verified shutdown buttons and screen

- Hold Power + Volume Up for three seconds and release both for orderly shutdown.
- Show the Platina logo, release version and Power off screen during shutdown.
- Preview, button handling and shutdown on battery were physically verified.
- Disconnect USB/the charger first to remain powered off. Attached power triggers
  a charger-mode boot and starts Linux again; this remains an accepted limitation.
- No experimental PMIC trigger changes are included in new images.

## 0.2.0 — verified integrated display

- Kernel 7.2.12-r1 integrates the Platina Tianma NT36672A panel and device tree.
- RAM boot, normal eMMC boot, logo, brightness and ten display off/on cycles passed
  physical testing. VSP/VSN full rail shutdown and power savings remain unproven.
- Display on/off/brightness/status, timed images and host-side image preparation.

## 0.1.1 — historical integration

- Headless postmarketOS from eMMC with key-only SSH over Wi-Fi or USB networking.
- NetworkManager reconnect and OpenRC autostart; corrected initramfs indexes.
- Seven-second boot logo using a temporary LCD helper, now superseded on the
  tested Tianma phone by the integrated driver.

The integration version is separate from the kernel and distribution versions.
