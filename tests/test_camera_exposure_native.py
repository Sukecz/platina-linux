"""Exercise sensor conversion code used by the actual ARM64 IPA build."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NativeExposureTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('c++'), 'A C++ compiler is required for sensor conversion checks')
    def test_sensor_line_conversion_and_gain_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / 'exposure'
            subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            '-I' + str(ROOT / 'project/camera/libcamera-headless'),
                            str(ROOT / 'tests/camera_exposure.cpp'), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)

    @unittest.skipUnless(shutil.which('c++'), 'A C++ compiler is required for crop checks')
    def test_zoom_coordinates_crop_geometry_and_wire_parser(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / 'zoom'
            subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror',
                            '-I' + str(ROOT / 'project/camera/libcamera-headless'),
                            str(ROOT / 'tests/camera_zoom.cpp'), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)
