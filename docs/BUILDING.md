# Building Platina Linux

This is a source-only development port. Kernel 7.2.12-r1 and the 0.3.1 in-place
runtime update were tested on a Tianma Mi 8 Lite. Source version 0.3.1 integrates
that runtime into newly built images; the new full image still requires its own
hardware acceptance. There is no ready-made stable release.

## Build host

Use Linux, Python 3.11+, Git, Make, a POSIX shell and sudo. The build creates
pmbootstrap chroots and needs Internet access, substantial disk space and time.
It uses two jobs at nice level 10. No host services or phones are restarted.

On Debian/Ubuntu, typical host tools are:

```sh
sudo apt install git python3 make sudo openssh-client e2fsprogs util-linux kmod mtools fastboot
# Required for the versioned boot/shutdown screens included by make images.
sudo apt install python3-pil fonts-dejavu-core
```

`make doctor` reports missing core tools without installing them. Kernel compilers
and package dependencies are installed inside the build chroots by pmbootstrap.
Python's standard library is enough for the basic offline test suite; the image
runtime integration tests and full image builder also need Pillow and DejaVu Sans.

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

## Integrated runtime and initramfs audit

`make images` builds the versioned boot logo and Power off screen, installs the
Python display/shutdown helpers and headless hook, and enables the OpenRC
Power + Volume Up service with the verified three-second policy. The image audit
checks file hashes, decoded frames, permissions and service links without touching
the display or invoking shutdown. No experimental PMIC module is included.

The USB current helper and NetworkManager dispatcher are also included. They are
inert without a separately supplied `/etc/platina/usb-power.json` policy; no host
identity or increased-current allowance is cloned from the development phone.
Wi-Fi credentials and monitoring credentials also remain per-installation inputs.

The mkinitfs version used by this port can copy full-rootfs module indexes into
an initramfs containing only some modules. The builder automatically regenerates
indexes for the modules actually included in the exported boot image. The final
boot.img and initramfs are hashed only after this correction. The unmodified
pmbootstrap export links are intermediate files, not the accepted output bundle.

Use boot.img and xiaomi-platina.img from the **same final candidate-local bundle**.
For manually exported older images, `scripts/scope-initramfs-modules.py` remains
available. The correction preserves the kernel, DTB and rootfs command line.

Exported files include boot.img, xiaomi-platina.img, initramfs, kernel and DTB.
Keep the manifest and corresponding APKs for your own rollback records.

## Separate display asset bundles

```sh
make splash
python3 scripts/prepare-display-frame.py your-image.png --output artifacts/custom-frame
```

The original logo is preserved; the integration version is added during rendering.
These commands create separate local bundles for review or an explicitly planned
existing-installation update. A fresh `make images` already includes both release
screens. See [display setup](DISPLAY.md) and [shutdown behavior](SHUTDOWN.md).
