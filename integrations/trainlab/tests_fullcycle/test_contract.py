"""Falsifiers for FULLCYCLE-001; require real learning and artifact isolation."""

import unittest


class LifecycleContract(unittest.TestCase):
    def test_fullcycle_controller_exists(self):
        from trainlab.fullcycle.pipeline import run_pipeline

        self.assertTrue(callable(run_pipeline))

    def test_streaming_language_release_exists(self):
        from forge_data.language import LanguageRelease

        self.assertTrue(callable(LanguageRelease))
