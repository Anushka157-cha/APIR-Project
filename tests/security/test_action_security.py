import sys
import unittest
sys.path.insert(0, "backend")
from app.action_registry import validate_action

class ActionSecurityTests(unittest.TestCase):
    def test_unknown_action_is_rejected(self):
        with self.assertRaises(ValueError): validate_action("restart_service; rm -rf /", "payment-service")
    def test_unknown_target_is_rejected(self):
        with self.assertRaises(ValueError): validate_action("restart_service", "payment-service; whoami")
    def test_known_action_is_allowlisted(self):
        self.assertEqual(validate_action("restart_service", "payment-service")["target"], "payment-service")

if __name__ == "__main__": unittest.main()
