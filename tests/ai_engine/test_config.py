import unittest

from ai_engine.config import AIEngineConfig


class AIEngineConfigTests(unittest.TestCase):
    def test_ai_engine_config_exposes_frame_cap_and_namespace_override(self):
        config = AIEngineConfig()

        self.assertEqual(config.max_total_frames, 600)
        self.assertEqual(config.model_config["protected_namespaces"], ("settings_",))


if __name__ == "__main__":
    unittest.main()
