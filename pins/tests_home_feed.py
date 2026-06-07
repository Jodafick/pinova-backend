from django.test import SimpleTestCase

from pins.home_feed import (
    compute_interleave_slots,
    home_feed_total_count,
    interleave_pin_lists,
)


class HomeFeedInterleaveTests(SimpleTestCase):
    def _mixed_via_slots(self, f_count, d_count, page_size, page_number=1):
        start = (page_number - 1) * page_size
        slots = compute_interleave_slots(f_count, d_count, start, page_size)
        labels = []
        for src, idx in slots:
            prefix = 'F' if src == 'following' else 'D'
            labels.append(f'{prefix}{idx + 1}')
        return labels

    def test_total_count(self):
        self.assertEqual(home_feed_total_count(0, 12), 12)
        self.assertEqual(home_feed_total_count(5, 7), 12)

    def test_page1_balanced_50_50(self):
        labels = self._mixed_via_slots(20, 20, 10, page_number=1)
        self.assertEqual(labels, ['F1', 'D1', 'F2', 'D2', 'F3', 'D3', 'F4', 'D4', 'F5', 'D5'])

    def test_page2_offsets(self):
        labels = self._mixed_via_slots(20, 20, 10, page_number=2)
        self.assertEqual(labels, ['F6', 'D6', 'F7', 'D7', 'F8', 'D8', 'F9', 'D9', 'F10', 'D10'])

    def test_following_exhausted_mid_stream(self):
        following = [f'F{i}' for i in range(1, 3)]
        discover = [f'D{i}' for i in range(1, 6)]
        expected = interleave_pin_lists(following, discover)
        slots = compute_interleave_slots(2, 5, 0, len(expected))
        rebuilt = []
        for src, idx in slots:
            rebuilt.append(following[idx] if src == 'following' else discover[idx])
        self.assertEqual(rebuilt, expected)

    def test_no_following_discover_only(self):
        labels = self._mixed_via_slots(0, 8, 10, page_number=1)
        self.assertEqual(labels, ['D1', 'D2', 'D3', 'D4', 'D5', 'D6', 'D7', 'D8'])

    def test_slots_match_legacy_interleave(self):
        following = list(range(100))
        discover = list(range(200, 250))
        legacy = interleave_pin_lists(following, discover)
        for page in (1, 2, 5, 10):
            page_size = 10
            start = (page - 1) * page_size
            slots = compute_interleave_slots(len(following), len(discover), start, page_size)
            rebuilt = []
            for src, idx in slots:
                rebuilt.append(following[idx] if src == 'following' else discover[idx])
            self.assertEqual(rebuilt, legacy[start : start + page_size], msg=f'page {page}')
