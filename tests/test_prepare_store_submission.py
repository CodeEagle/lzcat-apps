from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.prepare_store_submission import reward_opportunities, validate_screenshot_requirements


class PrepareStoreSubmissionTest(unittest.TestCase):
    def test_validate_screenshot_requirements_accepts_desktop_and_mobile_minimums(self) -> None:
        counts = validate_screenshot_requirements(
            [
                {"path": "desktop-1.png", "viewport": {"width": 1920, "height": 1080}},
                {"path": "desktop-2.png", "viewport": {"width": 1280, "height": 800}},
                {"path": "mobile-1.png", "viewport": {"width": 390, "height": 844}},
                {"path": "mobile-2.png", "viewport": {"width": 414, "height": 896}},
                {"path": "mobile-3.png", "viewport": {"width": 430, "height": 932}},
            ],
            desktop_required=2,
            mobile_required=3,
        )

        self.assertEqual(counts, {"desktop": 2, "mobile": 3})

    def test_validate_screenshot_requirements_rejects_missing_mobile_screenshots(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "desktop 2.*mobile 3"):
            validate_screenshot_requirements(
                [
                    {"path": "desktop-1.png", "viewport": {"width": 1920, "height": 1080}},
                    {"path": "desktop-2.png", "viewport": {"width": 1280, "height": 800}},
                    {"path": "mobile-1.png", "viewport": {"width": 390, "height": 844}},
                ],
                desktop_required=2,
                mobile_required=3,
            )

    def test_reward_opportunities_include_playground_and_integrations(self) -> None:
        keys = {item["key"] for item in reward_opportunities()}

        self.assertIn("self_hosted_migration", keys)
        self.assertIn("playground_guide", keys)
        self.assertIn("lazycat_account_integration", keys)
        self.assertIn("cloud_drive_integration", keys)


if __name__ == "__main__":
    unittest.main()
