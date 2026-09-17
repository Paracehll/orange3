from unittest.mock import patch
from Orange.widgets.data.owllm import OWLLM, call_llm_api, execute_llm_task, detect_provider, fetch_nvidia_models
from Orange.widgets.tests.base import WidgetTest


class TestOWLLM(WidgetTest):
    def setUp(self):
        self.widget = self.create_widget(OWLLM)

    def test_settings_default(self):
        self.assertEqual(self.widget.api_key, "")
        self.assertEqual(self.widget.provider_idx, 0)
        self.assertEqual(self.widget.parallel_count, 1)
        self.assertTrue(self.widget.retry)

    def test_detect_provider(self):
        self.assertEqual(detect_provider("sk-123", 1), "deepseek")
        self.assertEqual(detect_provider("key", 2), "gemini")
        self.assertEqual(detect_provider("key", 3), "nvidia")
        self.assertEqual(detect_provider("nvapi-123", 0), "nvidia")
        self.assertEqual(detect_provider("AIza123", 0), "gemini")

    @patch("urllib.request.urlopen")
    def test_fetch_nvidia_models(self, mock_urlopen):
        class MockResponse:
            def read(self):
                return b'{"data": [{"id": "meta/llama-3.1-70b-instruct"}, {"id": "meta/llama-3.1-8b-instruct"}]}'
            def __enter__(self):
                return self
            def __exit__(self, exc_type, exc_val, exc_tb):
                pass

        mock_urlopen.return_value = MockResponse()
        models = fetch_nvidia_models("nvapi-testkey")
        self.assertIn("meta/llama-3.1-70b-instruct", models)
        self.assertIn("meta/llama-3.1-8b-instruct", models)

    def test_inputs_and_outputs(self):
        self.send_signal(self.widget.Inputs.prompt, "Translate this")
        self.send_signal(self.widget.Inputs.skill, "Translator")
        self.send_signal(self.widget.Inputs.file, "Line 1\nLine 2\nLine 3")

        self.assertEqual(self.widget.input_prompt, "Translate this")
        self.assertEqual(self.widget.input_skill, "Translator")
        self.assertEqual(self.widget.input_file, "Line 1\nLine 2\nLine 3")

    @patch("Orange.widgets.data.owllm.call_llm_api")
    def test_commit_success(self, mock_call_llm):
        mock_call_llm.return_value = "Translated text"

        self.widget.api_key = "sk-test12345"
        self.send_signal(self.widget.Inputs.prompt, "Translate to French")
        self.send_signal(self.widget.Inputs.file, "Hello world")

        output = self.get_output(self.widget.Outputs.result)
        self.assertEqual(output, "Translated text")
        self.assertFalse(self.widget.Error.api_error.is_active())

    @patch("Orange.widgets.data.owllm.call_llm_api")
    def test_parallel_chunk_ordering(self, mock_call_llm):
        def mock_llm(prompt, key, provider, model_name=""):
            if "Chunk 1" in prompt:
                return "Res 1"
            elif "Chunk 2" in prompt:
                return "Res 2"
            return "Res 3"

        mock_call_llm.side_effect = mock_llm
        self.widget.api_key = "sk-test"
        self.widget.parallel_count = 2
        self.send_signal(self.widget.Inputs.file, "Chunk 1\nChunk 2")

        output = self.get_output(self.widget.Outputs.result)
        self.assertEqual(output, "Res 1\n\nRes 2")

    @patch("Orange.widgets.data.owllm.call_llm_api")
    def test_retry_on_failure(self, mock_call_llm):
        mock_call_llm.side_effect = [Exception("Key 1 failed"), "Key 2 success"]

        self.widget.api_key = "sk-key1, sk-key2"
        self.widget.retry = True

        res = execute_llm_task("test prompt", ["sk-key1", "sk-key2"], retry=True)
        self.assertEqual(res, "Key 2 success")
        self.assertEqual(mock_call_llm.call_count, 2)

    def test_no_api_key_error(self):
        self.widget.api_key = ""
        self.send_signal(self.widget.Inputs.prompt, "Test")
        output = self.get_output(self.widget.Outputs.result)
        self.assertIsNone(output)
        self.assertTrue(self.widget.Error.api_error.is_active())
