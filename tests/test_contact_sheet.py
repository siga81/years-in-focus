"""Regression tests for compact contact-sheet selection."""

from __future__ import annotations

import unittest

from facemovie.rendering.contact_sheet import _contact_sheet_items


class ContactSheetSelectionTests(unittest.TestCase):
    def test_large_set_is_capped_and_keeps_both_ends(self) -> None:
        items = list(range(4_000))

        selected = _contact_sheet_items(items, 200)

        self.assertEqual(len(selected), 200)
        self.assertEqual(selected[0], 0)
        self.assertEqual(selected[-1], 3_999)


if __name__ == "__main__":
    unittest.main()
