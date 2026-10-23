# Contributing

Start with the [feature status](README.md#feature-status), [build guide](docs/BUILDING.md)
and [hardware notes](docs/HARDWARE.md). Keep changes small and include the affected
phone model, panel variant, kernel version and the result you actually tested.

Edit recipes in `ports/candidate/`, update the matching SHA512 entries and package
revision, and keep `project/sources.lock.json` consistent. Do not edit generated
checkout files as the only source of a change. Run `make check` before submitting.
For hardware changes, distinguish a successful build from a real phone test.

Use 🟢 for physically verified functionality, 🟠 for partial support or work awaiting
hardware testing, and 🔴 for known non-working or unsupported functionality. Update
the README status table and date when evidence changes. Never promote a driver to
working simply because it exists in the kernel configuration.

Submit device logs after removing credentials, device identifiers, public keys,
local addresses and personal paths. Never commit firmware blobs, phone backups,
private configuration, generated images or agent instructions.

Original contributions are GPL-2.0-only unless a file states another applicable
license. Preserve third-party copyrights, SPDX identifiers and license notices;
see [licensing](docs/LICENSING.md). A pull request does not authorize flashing
someone else's device or changing their network.
