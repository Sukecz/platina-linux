# Building Platina Linux

This is a source-only development port. The candidate kernel builds, but the new
integrated Tianma display still needs its first successful physical boot test.
An image built here is a candidate, not a ready-made stable release.

## Build host

Use Linux, Python 3.11+, Git, Make, a POSIX shell and sudo. The build creates
pmbootstrap chroots and needs Internet access, substantial disk space and time.
It uses two jobs at nice level 10. No host services or phones are restarted.

On Debian/Ubuntu, typical host tools are:

```sh
sudo apt install git python3 make sudo openssh-client e2fsprogs util-linux kmod mtools fastboot
# Optional: only needed for make splash / custom image conversion.
sudo apt install python3-pil fonts-dejavu-core
```

`make doctor` reports missing core tools without installing them. Kernel compilers
and package dependencies are installed inside the build chroots by pmbootstrap.
Python's standard library is enough for the basic offline test suite; image
conversion uses Pillow on the build host.

## Personal build inputs

```sh
mkdir -p config
cp /PATH/TO/YOUR/ADMINISTRATOR-KEY.pub config/admin-builder.pub
```

Use a dedicated key if appropriate. Only its **public** half enters the image.
The user account is `server`, with passwordless sudo for administration. Password
and root SSH login are disabled. Keep the private key outside this repository.

Firmware is not distributed here. From a legally obtained matching stock ROM,
extract `images/NON-HLOS.bin` without running any ROM scripts, and obtain the
matching `a512_zap.elf` GPU firmware from your own vendor firmware. The pinned
reference is the Mi 8 Lite global stock firmware V12.0.3.0.QDTMIXM; other inputs
are rejected if their hashes differ.

The recipe expects three local inputs: `a512_zap.elf`,
`firmware-xiaomi-platina-bdwlan.tar.gz` and `firmware-xiaomi-platina-modem.tar.gz`.
The helper reads the FAT firmware image with mtools, creates deterministic
archives and checks all three against the recipe before writing them:

```sh
python3 scripts/prepare-firmware.py \
  --modem-image /PATH/TO/NON-HLOS.bin \
  --gpu-firmware /PATH/TO/a512_zap.elf
```

The output is `config/firmware/`, which is ignored by Git. Missing matching
firmware is a build prerequisite; this repository does not silently substitute
another phone's calibration, modem firmware or administrator key.

## Prepare and compile

```sh
make check
./scripts/project prepare --profile candidate --fetch
make kernel PROFILE=candidate
make images OUTPUT=candidate-local
make verify DIR=artifacts/candidate-local
make audit DIR=artifacts/candidate-local
```

Preparation pins pmbootstrap, pmaports and its channel table from
`project/sources.lock.json`. It creates a new managed checkout and refuses to
overwrite one. After changing a versioned recipe, run `make sync` before rebuilding.
Checksum checks parse APKBUILD as text rather than executing its shell on the host.

The image contains the public key and proprietary firmware you provided. It is
therefore **your local installation image**, not automatically a public artifact.
The builder stops pmbootstrap mounts before copying/hashing filesystem images.
Source revisions are pinned, but external Alpine repositories/toolchain packages
are not fully frozen; bit-for-bit reproducible full builds are not promised.

## Scope initramfs module indexes

The mkinitfs version used by this port can copy full-rootfs module indexes into
an initramfs containing only some modules. Before booting or flashing, regenerate
indexes for the modules that are actually included:

```sh
python3 scripts/scope-initramfs-modules.py artifacts/candidate-local/boot.img \
  --release 7.2.12-sdm660 --output artifacts/candidate-local-scoped
make verify DIR=artifacts/candidate-local-scoped
```

Use **candidate-local-scoped/boot.img** with **candidate-local/xiaomi-platina.img**.
The scoping tool preserves the kernel, DTB and rootfs command line; it does not
create a second root filesystem and does not flash anything.

Exported files include boot.img, xiaomi-platina.img, initramfs, kernel and DTB.
Keep the manifest and corresponding APKs for your own rollback records.

## Optional display assets

```sh
make splash
python3 scripts/prepare-display-frame.py your-image.png --output artifacts/custom-frame
```

The original logo is preserved; the integration version is added during rendering.
These commands create local bundles. `make images` does not yet install the
versioned splash bundle automatically; see [display setup](DISPLAY.md).
