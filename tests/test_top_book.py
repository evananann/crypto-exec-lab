import unittest

from cel.ingest.top_book import TopBook


class TopBookTests(unittest.TestCase):
    def test_one_sided_delta_keeps_the_other_side(self) -> None:
        book = TopBook()
        self.assertTrue(book.apply([["100.0", "1"]], [["100.1", "1"]]))
        self.assertTrue(book.apply([["99.9", "2"]], []))
        self.assertEqual(book.bid, 99.9)
        self.assertEqual(book.ask, 100.1)

    def test_zero_size_clears_that_side(self) -> None:
        book = TopBook()
        book.apply([["100.0", "1"]], [["100.1", "1"]])
        self.assertFalse(book.apply([["100.0", "0"]], []))
        self.assertIsNone(book.bid)
