from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_build import extract_lazycat_image_overrides_from_manifest


class RunBuildImagesTest(unittest.TestCase):
    def test_extracts_lazycat_images_from_manifest_services(self) -> None:
        manifest = """
services:
  web:
    image: registry.lazycat.cloud/invokerlaw/codeeagle/demo:abc
    binds:
      - /lzcapp/var/data:/data
  worker:
    image: ghcr.io/example/worker:latest
"""

        overrides = extract_lazycat_image_overrides_from_manifest(manifest)

        self.assertEqual(overrides, {"web": "registry.lazycat.cloud/invokerlaw/codeeagle/demo:abc"})


if __name__ == "__main__":
    unittest.main()
