"""Archive preparation must remain offline, selective and non-destructive."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from research.roadmap.preserve_soak import preserve


class SoakPreservationTests(unittest.TestCase):
    def fixture(self, root):
        private, report = root / "private", root / "public"
        (private / "spool").mkdir(parents=True)
        report.mkdir()
        (private / "spool" / "fixture.status.json").write_text("{}")
        (private / "config.json").write_text('{"public_feeds_only":true}')
        (report / "protocol.json").write_text(
            json.dumps(
                {
                    "scope": "Independent cloud acquisition qualification only; zero strategy outcomes",
                    "source_sha256": {},
                }
            )
        )
        (report / "report.json").write_text(json.dumps({"strategy_outcomes_evaluated": 0}))
        return private, report

    def test_prepare_only_never_calls_github_and_changed_inputs_are_refused(self):
        with (
            tempfile.TemporaryDirectory() as temp,
            patch("research.roadmap.preserve_soak.gh") as github,
        ):
            private, report = self.fixture(Path(temp))
            result = preserve(
                private, report, "qualification-cloud-fixture", "0" * 40, prepare_only=True
            )
            self.assertFalse(result["remote_readback_verified"])
            self.assertTrue((private / "publication" / "qualification.tar.gz").is_file())
            github.assert_not_called()
            (private / "config.json").write_text('{"changed":true}')
            with self.assertRaises(ValueError):
                preserve(
                    private, report, "qualification-cloud-fixture", "0" * 40, prepare_only=True
                )

    def test_symlink_and_unexpected_spool_inputs_are_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            private, report = self.fixture(Path(temp))
            (private / "spool" / "unrelated.env").write_text("synthetic fixture, not a credential")
            with self.assertRaises(ValueError):
                preserve(
                    private, report, "qualification-cloud-fixture", "0" * 40, prepare_only=True
                )
            (private / "spool" / "unrelated.env").unlink()
            (private / "spool" / "linked.json").symlink_to(private / "config.json")
            with self.assertRaises(ValueError):
                preserve(
                    private, report, "qualification-cloud-fixture", "0" * 40, prepare_only=True
                )


if __name__ == "__main__":
    unittest.main()
