import unittest

from ai_engine.fusion.timeline import Timeline


class TimelineWindowQueryTests(unittest.TestCase):
    def test_find_event_near_returns_closest_match_in_window(self):
        timeline = Timeline()
        timeline.add_event(8.0, "kneeling", "video")
        timeline.add_event(11.0, "kneeling", "video")
        timeline.add_event(20.0, "kneeling", "video")

        event = timeline.find_event_near("kneeling", center_time=10.0, window=3.0)

        self.assertIsNotNone(event)
        self.assertEqual(event["time"], 11.0)

    def test_find_events_near_returns_all_matches_in_window(self):
        timeline = Timeline()
        timeline.add_event(4.0, "standing_nearby", "video")
        timeline.add_event(7.0, "standing_nearby", "video")
        timeline.add_event(12.5, "standing_nearby", "video")

        events = timeline.find_events_near(
            "standing_nearby", center_time=8.0, window=4.5
        )

        self.assertEqual([event["time"] for event in events], [4.0, 7.0, 12.5])


if __name__ == "__main__":
    unittest.main()
