import unittest
from types import SimpleNamespace

from llm_client import extract_chat_content


class ExtractChatContentTests(unittest.TestCase):
    def test_extracts_plain_text_response(self):
        self.assertEqual(extract_chat_content("model output"), "model output")

    def test_extracts_openai_chat_completion_response(self):
        response = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="model output"))]
        )
        self.assertEqual(extract_chat_content(response), "model output")

    def test_rejects_unsupported_response(self):
        with self.assertRaisesRegex(ValueError, "unsupported chat completion response"):
            extract_chat_content(object())


if __name__ == "__main__":
    unittest.main()
