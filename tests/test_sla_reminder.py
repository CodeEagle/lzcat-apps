from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.sla_reminder import _parse_iso, render_markdown, stale_awaiting_human


def _item(slug: str, status: str, *, last_run: str = "", upstream: str = "", archived: bool = False) -> dict:
    fields = []
    if slug:
        fields.append({"field": {"id": "F_slug", "name": "Slug"}, "text": slug})
    fields.append({"field": {"id": "F_status", "name": "Status"}, "name": status, "optionId": "opt"})
    if last_run:
        fields.append({"field": {"id": "F_run", "name": "Last Run"}, "date": last_run})
    if upstream:
        fields.append({"field": {"id": "F_up", "name": "Upstream"}, "text": upstream})
    return {"id": f"PVTI_{slug}", "isArchived": archived, "fieldValues": {"nodes": fields}}


class StaleAwaitingHumanTest(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 5, 6, 12, 0, 0, tzinfo=timezone.utc)

    def test_picks_up_item_with_no_last_run(self) -> None:
        items = [_item("alpha", "Awaiting-Human")]
        stale = stale_awaiting_human(items, now=self.now)
        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0]["slug"], "alpha")
        self.assertIsNone(stale[0]["stale_hours"])

    def test_picks_up_item_older_than_sla(self) -> None:
        items = [_item("alpha", "Awaiting-Human", last_run="2026-05-05T11:00:00Z")]
        stale = stale_awaiting_human(items, now=self.now)
        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0]["stale_hours"], 25.0)

    def test_skips_item_within_sla(self) -> None:
        items = [_item("alpha", "Awaiting-Human", last_run="2026-05-06T08:00:00Z")]
        self.assertEqual(stale_awaiting_human(items, now=self.now), [])

    def test_skips_non_awaiting_status(self) -> None:
        items = [_item("alpha", "In-Progress"), _item("bravo", "Approved")]
        self.assertEqual(stale_awaiting_human(items, now=self.now), [])

    def test_skips_archived(self) -> None:
        items = [_item("alpha", "Awaiting-Human", archived=True)]
        self.assertEqual(stale_awaiting_human(items, now=self.now), [])

    def test_custom_sla_hours(self) -> None:
        items = [_item("alpha", "Awaiting-Human", last_run="2026-05-06T08:00:00Z")]
        stale = stale_awaiting_human(items, now=self.now, sla_hours=2)
        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0]["stale_hours"], 4.0)

    def test_render_markdown_empty(self) -> None:
        out = render_markdown([], sla_hours=24)
        self.assertIn("No Awaiting-Human", out)

    def test_render_markdown_summary(self) -> None:
        out = render_markdown(
            [
                {"slug": "alpha", "upstream": "github.com/x/alpha", "branch": "", "pr": "", "last_run": "", "stale_hours": None},
                {"slug": "bravo", "upstream": "", "branch": "", "pr": "https://gh/pr/1", "last_run": "2026-05-04T00:00:00+00:00", "stale_hours": 60.0},
            ],
            sla_hours=24,
        )
        self.assertIn("`alpha`", out)
        self.assertIn("`bravo`", out)
        self.assertIn("PR: https://gh/pr/1", out)
        self.assertIn("60.0h", out)

    def test_parse_iso_handles_z_and_offsets(self) -> None:
        self.assertEqual(
            _parse_iso("2026-05-06T12:00:00Z"),
            datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(
            _parse_iso("2026-05-06T12:00:00+00:00"),
            datetime(2026, 5, 6, 12, 0, tzinfo=timezone.utc),
        )
        # Naive ISO gets coerced to UTC.
        self.assertEqual(
            _parse_iso("2026-05-06T12:00:00").tzinfo,
            timezone.utc,
        )
        self.assertIsNone(_parse_iso(""))
        self.assertIsNone(_parse_iso("not a date"))


if __name__ == "__main__":
    unittest.main()
