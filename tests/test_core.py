
import unittest
import os
import sys
from unittest.mock import MagicMock, patch

# Add python directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../python/legion_linux')))

from legion_linux import legion

class TestLegionCore(unittest.TestCase):
    def setUp(self):
        pass

    @patch('legion_linux.legion.FanCurveIO._find_hwmon_dir')
    def test_model_initialization(self, mock_find_hwmon):
        mock_find_hwmon.return_value = "/tmp/mock_hwmon/"
        model = legion.LegionModelFacade(expect_hwmon=False)
        self.assertIsNotNone(model)

    @patch('builtins.open', new_callable=unittest.mock.mock_open, read_data="100")
    def test_read_file(self, mock_file):
        # Test the optimized _read_file method
        val = legion.FanCurveIO._read_file("/tmp/test_file")
        self.assertEqual(val, 100)
        mock_file.assert_called_with("/tmp/test_file", 'r')

if __name__ == '__main__':
    unittest.main()
