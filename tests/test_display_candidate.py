"""Verify the Tianma candidate matches the retained stock initialization data."""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DisplayCandidateTests(unittest.TestCase):
    def test_init_packets_and_delays_match_stock_panel(self):
        reference = json.loads((ROOT / 'project/display/tianma-reference.json').read_text())
        raw = bytes.fromhex(reference['on_command_hex'])
        expected = []
        offset = 0
        while offset < len(raw):
            header = raw[offset:offset + 7]
            size = int.from_bytes(header[5:7], 'big')
            payload = raw[offset + 7:offset + 7 + size]
            self.assertEqual(len(payload), size)
            # Downstream encodes a dummy second byte for DCS no-param packets.
            if header[0] == 0x05:
                self.assertEqual(payload[1:], b'\0')
                payload = payload[:1]
            expected.append(('generic' if header[0] == 0x29 else 'dcs', payload))
            if header[4]:
                expected.append(('delay', header[4]))
            offset += 7 + size
        self.assertEqual(offset, len(raw))
        patch = (ROOT / 'ports/candidate/linux-postmarketos-qcom-sdm660/0030-platina-tianma-panel.patch').read_text()
        added = '\n'.join(line[1:] for line in patch.splitlines()
                          if line.startswith('+') and not line.startswith('+++'))
        init = added.split('static void platina_tianma_init_cmds', 1)[1].split('\n}', 1)[0]
        actual = []
        for line in init.splitlines():
            write = re.search(r'mipi_dsi_(generic|dcs)_write_seq_multi\(dsi_ctx, (.*?)\);', line)
            delay = re.search(r'mipi_dsi_msleep\(dsi_ctx, (\d+)\);', line)
            if write:
                actual.append((write[1], bytes(int(v.strip(), 16) for v in write[2].split(','))))
            elif delay:
                actual.append(('delay', int(delay[1])))
        self.assertEqual(len([v for v in expected if v[0] != 'delay']), 180)
        self.assertEqual(actual, expected)


if __name__ == '__main__':
    unittest.main()
