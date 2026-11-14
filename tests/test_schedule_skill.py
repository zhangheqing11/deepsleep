from __future__ import annotations

import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from domain.schedule import ScheduleBlock, ScheduleProfile, build_schedule_context, find_conflicts
from engine.schedule_skill import ScheduleProfileStore, load_schedule_context


class TestScheduleDomain(unittest.TestCase):
    def test_build_context_contains_only_schedule_constraints(self):
        profile = ScheduleProfile(
            (
                ScheduleBlock(weekday=0, start="09:00", end="17:30", kind="work"),
                ScheduleBlock(
                    weekday=2,
                    start="22:00",
                    end="01:00",
                    kind="class",
                    flexible_minutes=30,
                ),
            )
        )

        context = build_schedule_context(profile)

        self.assertEqual(len(context["weekly_commitments"]), 2)
        self.assertEqual(context["weekly_commitments"][0]["day"], "周一")
        self.assertTrue(context["weekly_commitments"][1]["ends_next_day"])
        self.assertEqual(context["weekly_commitments"][1]["flexible_minutes"], 30)
        self.assertNotIn("name", context)
        self.assertIn("先询问用户", context["guidance"])

    def test_empty_profile_has_no_agent_context(self):
        self.assertIsNone(build_schedule_context(ScheduleProfile(blocks=())))

    def test_conflicts_include_overnight_and_week_wrap(self):
        profile = ScheduleProfile(
            (ScheduleBlock(weekday=6, start="22:00", end="01:00", kind="work"),)
        )

        self.assertEqual(
            find_conflicts(profile, weekday=6, start="23:30", end="00:30"),
            profile.blocks,
        )
        self.assertEqual(find_conflicts(profile, weekday=0, start="01:00", end="02:00"), ())
        self.assertEqual(find_conflicts(profile, weekday=0, start="00:30", end="02:00"), profile.blocks)

    def test_adjacent_windows_do_not_conflict(self):
        profile = ScheduleProfile(
            (ScheduleBlock(weekday=0, start="09:00", end="17:00", kind="work"),)
        )
        self.assertEqual(find_conflicts(profile, weekday=0, start="17:00", end="18:00"), ())

    def test_invalid_blocks_are_rejected(self):
        with self.assertRaises(ValueError):
            ScheduleBlock(weekday=7, start="09:00", end="17:00", kind="work")
        with self.assertRaises(ValueError):
            ScheduleBlock(weekday=0, start="09:00", end="09:00", kind="work")
        with self.assertRaises(ValueError):
            ScheduleBlock(weekday=0, start="09:00", end="17:00", kind=[])
        with self.assertRaises(ValueError):
            ScheduleBlock(weekday=0, start="09:00", end="17:00", kind="work", flexible_minutes=241)
        with self.assertRaises(ValueError):
            find_conflicts(
                ScheduleProfile(blocks=()),
                weekday=0,
                start="09:00",
                end="09:00",
            )


class TestScheduleProfileStore(unittest.TestCase):
    def test_consent_round_trip_context_and_delete(self):
        profile = ScheduleProfile(
            (ScheduleBlock(weekday=1, start="08:30", end="16:30", kind="class"),)
        )
        with tempfile.TemporaryDirectory() as directory:
            store = ScheduleProfileStore(pathlib.Path(directory) / "profile.json")

            with self.assertRaises(PermissionError):
                store.save(profile, consent_granted=False)
            self.assertFalse(store.path.exists())

            store.save(profile, consent_granted=True)
            self.assertEqual(store.load(), profile)
            self.assertEqual(len(load_schedule_context(store)["weekly_commitments"]), 1)
            self.assertTrue(store.delete())
            self.assertFalse(store.delete())
            self.assertIsNone(store.load())

    def test_invalid_stored_json_is_not_silently_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            store = ScheduleProfileStore(pathlib.Path(directory) / "profile.json")
            store.path.write_text("{broken", encoding="utf-8")
            with self.assertRaises(ValueError):
                store.load()


if __name__ == "__main__":
    unittest.main()
