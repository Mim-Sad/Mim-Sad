import datetime as dt
import os
import sys
import tempfile
import unittest
import xml.dom.minidom as minidom
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
os.environ["PROFILE_OUT"] = tempfile.mkdtemp()

import profile_cards as pc  # noqa: E402


def day(offset, count, end=dt.date(2026, 1, 31)):
    return {"date": (end - dt.timedelta(days=offset)).isoformat(), "count": count}


class StreakTests(unittest.TestCase):
    def test_current_and_longest(self):
        days = [day(o, c) for o, c in zip(range(9, -1, -1), [1, 1, 1, 1, 0, 2, 2, 0, 3, 3])]
        self.assertEqual(pc.streaks(days), (2, 4))

    def test_empty_today_does_not_break_streak(self):
        days = [day(o, c) for o, c in zip(range(3, -1, -1), [1, 1, 1, 0])]
        self.assertEqual(pc.streaks(days)[0], 3)

    def test_no_activity(self):
        self.assertEqual(pc.streaks([day(1, 0), day(0, 0)]), (0, 0))

    def test_weekday_totals(self):
        # 2026-01-31 is a Saturday -> index 6 (Sun=0)
        self.assertEqual(pc.weekday_totals([day(0, 5)])[6], 5)


class RenderTests(unittest.TestCase):
    def test_all_svgs_are_well_formed(self):
        pc.build_static()
        pc.build_dynamic(pc.mock_data())
        files = list(pc.OUT.glob("*.svg"))
        self.assertEqual(len(files), 2 * (1 + len(pc.TOOLKIT) + len(pc.CARDS)))
        for f in files:
            minidom.parse(str(f))

    def test_handles_empty_account(self):
        data = pc.mock_data()
        data["days"] = [{"date": d["date"], "count": 0} for d in data["days"]]
        data["langs"] = {}
        pc.build_dynamic(data)  # must not raise ZeroDivisionError

    def test_language_names_are_escaped(self):
        data = pc.mock_data()
        data["langs"]["<script>"] = {"size": 10, "color": "#fff"}
        self.assertNotIn("<script>", pc.languages_card(data, pc.THEMES["dark"]))

    def test_toolkit_pills_stay_inside_card(self):
        import re
        for key in pc.TOOLKIT:
            svg, _ = pc.toolkit_card(key, pc.THEMES["light"])
            for x, w in re.findall(r'<rect x="([\d.]+)" y="[\d.]+" width="([\d.]+)" height="28"', svg):
                self.assertLessEqual(float(x) + float(w), pc.X1 + 0.5)

    def test_icon_contrast_fallback(self):
        self.assertLess(pc.contrast("#FFFFFF", pc.THEMES["light"]["chip"]), 2.2)

    def test_fmt(self):
        self.assertEqual(pc.fmt(999), "999")
        self.assertEqual(pc.fmt(12_000), "12k")


if __name__ == "__main__":
    unittest.main()
