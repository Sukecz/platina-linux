"""Keep Android lane descriptors distinct from the CSID hardware lane numbers."""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CameraLaneMappingTests(unittest.TestCase):
    def test_receiver_uses_the_stock_driver_translation(self):
        reference = json.loads((ROOT / 'project/camera/reference.json').read_text())
        mapping = reference['lane_mapping']
        android = int(reference['android_reference_only']['csi']['lane_assignment'], 16)
        # Xiaomi msm_csid.c translates each nibble through the hardware table.
        translated = [mapping['stock_table'][(android >> (4 * lane)) & 15]
                      for lane in range(4)]
        patch = (ROOT / 'ports/candidate/linux-postmarketos-qcom-sdm660/0032-platina-rear-camera.patch').read_text()
        receiver = patch.split('platina_csiphy0_ep: endpoint {', 1)[1].split('remote-endpoint', 1)[0]
        configured = [int(n) for n in re.search(r'data-lanes = <([^>]+)>', receiver)[1].split()]
        self.assertEqual(configured, translated)
        self.assertEqual(sum(n << (4 * i) for i, n in enumerate(configured)),
                         int(mapping['hardware_lane_assign'], 16))
        self.assertNotIn('clock-lanes', receiver)


if __name__ == '__main__':
    unittest.main()
