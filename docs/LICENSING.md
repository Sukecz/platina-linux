# Licensing

## Decision

**GPL-2.0-only** is the license for original Platina integration contributions,
including original scripts, tests, documentation and the supplied logo, unless
an individual file specifies otherwise. See [LICENSE](../LICENSE) and [NOTICE](../NOTICE).

The main reason is practical: this is a Linux kernel/device port, and its kernel
patches should remain usable under Linux's GPLv2 terms. This does not mean that
all software running on the phone has to use GPLv2.

| Option considered | Fit for this project |
|---|---|
| MIT | Good for permissive standalone tools; would not remove inherited kernel/copyleft requirements |
| Apache-2.0 | Explicit patent terms, but not compatible with GPL-2.0-only kernel combinations |
| GPL-3.0-only | Useful for many projects; cannot simply replace Linux's GPL-2.0-only terms |
| **GPL-2.0-only** | **Chosen for original integration work and kernel changes; matches the kernel's licensing baseline** |

Sources: [Linux kernel licensing rules](https://docs.kernel.org/process/license-rules.html),
[GNU license compatibility](https://www.gnu.org/licenses/license-list.html), and
[Apache's GPL compatibility explanation](https://apache.org/licenses/GPL-compatibility.html).

## Third-party material keeps its license

This source repository is an aggregate, not a claim that all included components
are one GPLv2 program. Existing copyrights and SPDX notices are retained.

- **Kernel patches/configuration:** kernel GPLv2 terms and relevant per-file SPDX
  identifiers. Some files allow later GPL versions or have compatible dual licenses.
- **Inherited pmaports packaging:** GPLv3 where the upstream packaging
  license applies. The package's `license=` field describes its installed payload;
  it is not by itself a license grant for every packaging script.
- **Device data:** MIT as declared by the community device package, with original
  author/maintainer attribution retained. Applicable kernel DT notices still apply.
- **Public firmware recipe and board-index helper:** newly written GPL-2.0-only
  source. The public firmware revision is 2-r5 to distinguish this packaging change.
- **Firmware binaries:** proprietary and absent from this Git repository. Each
  builder supplies matching inputs locally and must respect their own usage rights.
- **Camera/software ISP:** upstream libcamera licenses remain applicable. Changes
  to LGPL sources and the explicitly marked exposure/zoom helpers retain
  LGPL-2.1-or-later. The original camera consumer is GPL-2.0-only. See the
  included LGPL-2.1 text and the original SPDX/author notices.
- **Mesa/Freedreno and other camera dependencies:** fetched separately by recipes;
  their component licenses are not replaced by the integration's GPLv2 license.
- **External toolchains/packages:** retain their own licenses; the source repository
  does not vendor the full distro or claim ownership of those projects.

The upstream community repository has no blanket top-level LICENSE at the time
of this review. We therefore preserve its explicit kernel/device notices and do
not redistribute its firmware helper under an invented blanket license.
Full attribution and license texts are in NOTICE and LICENSES/.

## Source publication versus image publication

This public release contains source and the project logo. It does not
publish APKs, prebuilt disk/boot images, stock ROMs or device calibration backups.
Building a local image does not automatically grant permission to redistribute
its proprietary firmware, nor make a personalized SSH key/configuration public.

Any future binary release requires a separate component/source and firmware-rights
review. A GPL-covered kernel binary must be accompanied by the corresponding
source and notices under the applicable license terms. Existing third-party
rights are preserved; the repository's project license cannot replace them.
