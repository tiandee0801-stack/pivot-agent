"""Behavior tests use synthetic angle observations, not model accuracy data."""
import math
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from video_engine.counter import CurlCounter, elbow_angle
from video_engine.vision import probe_video, quality_reasons, VideoError


def feed(counter, values, start=0.0, dt=0.125):
    events = []
    t = start
    for value in values:
        event = counter.update(t, value, value is not None)
        if event:
            events.append(event)
        t += dt
    return t, events


CYCLE = [165]*4 + [140, 115, 90] + [55]*4 + [90, 115, 140] + [165]*4


class CounterBehaviorTests(unittest.TestCase):
    def test_interval_requires_two_completions(self):
        c = CurlCounter()
        feed(c, CYCLE)
        self.assertIsNone(c.cycle_duration_seconds)
        feed(c, CYCLE, start=len(CYCLE) * 0.125)
        self.assertEqual(c.cycle_duration_seconds, len(CYCLE) * 0.125)

    def test_interval_does_not_bridge_occlusion(self):
        c = CurlCounter()
        feed(c, CYCLE + [None] + CYCLE)
        self.assertEqual(c.count, 2)
        self.assertIsNone(c.cycle_duration_seconds)

    def test_interval_does_not_bridge_timestamp_gap(self):
        c = CurlCounter()
        t, _ = feed(c, CYCLE)
        feed(c, CYCLE, start=t + 1)
        self.assertEqual(c.count, 2)
        self.assertIsNone(c.cycle_duration_seconds)

    def test_interval_does_not_include_long_rest(self):
        c = CurlCounter()
        feed(c, CYCLE + [165] * 120 + CYCLE)
        self.assertEqual(c.count, 2)
        self.assertIsNone(c.cycle_duration_seconds)

    def test_one_full_cycle(self):
        c = CurlCounter()
        _, events = feed(c, CYCLE)
        self.assertEqual(c.count, 1)
        self.assertEqual(events.count('cycle_completed'), 1)

    def test_two_cycles_and_hold_does_not_duplicate(self):
        c = CurlCounter()
        feed(c, CYCLE + [165]*10 + CYCLE)
        self.assertEqual(c.count, 2)

    def test_flexion_only_is_not_completed(self):
        c = CurlCounter()
        feed(c, CYCLE[:11])
        self.assertEqual(c.count, 0)

    def test_starting_flexed_does_not_invent_start(self):
        c = CurlCounter()
        feed(c, [50]*5 + [100, 130] + [165]*5)
        self.assertEqual(c.count, 0)

    def test_partial_motion_is_not_rep(self):
        c = CurlCounter()
        feed(c, [165]*5 + [140, 120, 100]*3 + [165]*5)
        self.assertEqual(c.count, 0)

    def test_occlusion_resets_incomplete_cycle(self):
        c = CurlCounter()
        feed(c, CYCLE[:11] + [None] + CYCLE[11:])
        self.assertEqual(c.count, 0)

    def test_long_gap_resets_incomplete_cycle(self):
        c = CurlCounter()
        t, _ = feed(c, CYCLE[:11])
        feed(c, CYCLE[11:], start=t+1)
        self.assertEqual(c.count, 0)

    def test_timestamp_not_wall_clock(self):
        c = CurlCounter()
        # These calls run without sleeping, as they do during offline inference.
        feed(c, CYCLE)
        self.assertEqual(c.count, 1)

    def test_non_monotonic_timestamps_fail_and_reset(self):
        c = CurlCounter()
        feed(c, CYCLE[:11])
        with self.assertRaises(ValueError):
            c.update(0.1, 165)
        self.assertEqual(c.phase, 'waiting')
        self.assertEqual(c.count, 0)

    def test_single_frame_spike_not_rep(self):
        c = CurlCounter()
        feed(c, [165]*6 + [50] + [165]*6)
        self.assertEqual(c.count, 0)

    def test_static_zero_is_legitimate(self):
        c = CurlCounter()
        feed(c, [165]*40)
        self.assertEqual(c.count, 0)

    def test_invalid_angle_is_observation_loss(self):
        for angle in (float('nan'), float('inf'), -5, 190):
            c = CurlCounter()
            self.assertEqual(c.update(0, angle), 'observation_lost')

    def test_left_and_right_have_different_indices(self):
        points = [[0, 0, 0] for _ in range(17)]
        points[5], points[7], points[9] = [0.3, 0.2, 0.9], [0.3, 0.4, 0.9], [0.3, 0.6, 0.9]
        points[6], points[8], points[10] = [0.6, 0.2, 0.9], [0.6, 0.4, 0.9], [0.8, 0.4, 0.9]
        self.assertAlmostEqual(elbow_angle(points, 'left'), 180)
        self.assertAlmostEqual(elbow_angle(points, 'right'), 90)
        points[9][2] = 0.1
        self.assertIsNone(elbow_angle(points, 'left'))
        self.assertAlmostEqual(elbow_angle(points, 'right'), 90)

    def test_degenerate_segment_is_unusable(self):
        points = [[0.3, 0.2, 0.9] for _ in range(17)]
        self.assertIsNone(elbow_angle(points, 'left'))


class VideoQualityTests(unittest.TestCase):
    def test_static_visible_video_can_truthfully_report_zero(self):
        c = CurlCounter()
        feed(c, [165] * 32)
        self.assertEqual(c.count, 0)
        self.assertEqual(quality_reasons(30, 1, 32, 0, False, False), [])
        self.assertIsNone(c.cycle_duration_seconds)

    def test_nonvisible_refuses_summary(self):
        reasons = quality_reasons(30, 0, 0, 4, False, False)
        self.assertIn('insufficient_valid_ratio', reasons)
        self.assertIn('continuous_observation_lost', reasons)

    def test_multiple_person_always_refuses_even_valid_arm(self):
        self.assertIn('multiple_people', quality_reasons(30, 1, 100, 0, False, True))

    def test_discontinuity_refuses(self):
        self.assertIn('subject_discontinuity', quality_reasons(30, 1, 100, 0, True, False))

    def test_low_fps_short_visibility_and_long_gap_refuse(self):
        self.assertIn('frame_rate_too_low', quality_reasons(7, 1, 100, 0, False, False))
        self.assertIn('insufficient_visible_duration', quality_reasons(30, 1, 15, 0, False, False))
        self.assertIn('continuous_observation_lost', quality_reasons(30, .95, 100, .6, False, False))


class VideoMetadataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'sample.mp4'
        self.path.write_bytes(b'probe-result-is-mocked')
        self.stream = {'codec_type': 'video', 'codec_name': 'h264', 'width': 640,
                       'height': 480, 'avg_frame_rate': '30/1', 'duration': '4.0'}

    def tearDown(self):
        self.tmp.cleanup()

    def probe(self, **overrides):
        stream = dict(self.stream, **overrides)
        with patch('video_engine.vision.subprocess.run') as run:
            run.return_value.stdout = json.dumps({'streams': [stream], 'format': {'duration': '4.0'}}).encode()
            return probe_video(self.path)

    def test_probe_disallows_network_protocols_and_playlist_demuxers(self):
        with patch('video_engine.vision.subprocess.run') as run:
            run.return_value.stdout = json.dumps({'streams': [self.stream], 'format': {'duration': '4.0'}}).encode()
            probe_video(self.path)
            args = run.call_args.args[0]
            self.assertEqual(args[args.index('-protocol_whitelist')+1], 'file,pipe')
            self.assertEqual(args[args.index('-enable_drefs')+1], '0')
            self.assertEqual(args[args.index('-format_whitelist')+1], 'mov,matroska,webm')

    def test_ordinary_metadata_accepted(self):
        self.assertEqual(self.probe()['fps'], 30)

    def test_rotation_requires_normalized_source(self):
        with self.assertRaises(VideoError):
            self.probe(side_data_list=[{'rotation': 90}])

    def test_too_long_rejected_before_model_load(self):
        with self.assertRaises(VideoError):
            self.probe(duration='46.0')

    def test_invalid_fps_and_dimension_rejected(self):
        for overrides in ({'avg_frame_rate': '0/0'}, {'avg_frame_rate': '240/1'},
                          {'width': 100000}, {'width': 1}, {'duration': 'nan'}):
            with self.subTest(overrides=overrides), self.assertRaises(VideoError):
                self.probe(**overrides)

    def test_empty_file_rejected(self):
        self.path.write_bytes(b'')
        with self.assertRaises(VideoError):
            probe_video(self.path)


if __name__ == '__main__':
    unittest.main()
