import os
from pathlib import Path
import tempfile
import unittest

from tools.verify_live_ai_market_deployment import _load_named_environment_value


class VerifyLiveAIMarketDeploymentTests(unittest.TestCase):
    def test_loader_reads_only_named_value_and_handles_export_quotes(self):
        original_key = os.environ.get("TEST_OPENAI_KEY")
        original_other = os.environ.get("DO_NOT_IMPORT")
        try:
            os.environ.pop("TEST_OPENAI_KEY", None)
            os.environ.pop("DO_NOT_IMPORT", None)
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "service.env"
                path.write_text(
                    "DO_NOT_IMPORT=private-value\n"
                    "export TEST_OPENAI_KEY='test-value'\n",
                    encoding="utf-8",
                )
                _load_named_environment_value(path, "TEST_OPENAI_KEY")
            self.assertEqual(os.environ.get("TEST_OPENAI_KEY"), "test-value")
            self.assertIsNone(os.environ.get("DO_NOT_IMPORT"))
        finally:
            if original_key is None:
                os.environ.pop("TEST_OPENAI_KEY", None)
            else:
                os.environ["TEST_OPENAI_KEY"] = original_key
            if original_other is None:
                os.environ.pop("DO_NOT_IMPORT", None)
            else:
                os.environ["DO_NOT_IMPORT"] = original_other


if __name__ == "__main__":
    unittest.main()
