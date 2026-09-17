from unittest.mock import patch
from Orange.widgets.data.owspider import OWSpider, fetch_url
from Orange.widgets.tests.base import WidgetTest


class TestOWSpider(WidgetTest):
    def setUp(self):
        self.widget = self.create_widget(OWSpider)

    def test_settings_default(self):
        self.assertEqual(self.widget.url, "https://orange.biolab.si")
        self.assertEqual(self.widget.max_depth, 1)
        self.assertEqual(self.widget.max_pages, 5)
        self.assertEqual(self.widget.timeout, 10)

    @patch("Orange.widgets.data.owspider.fetch_url")
    def test_commit_success(self, mock_fetch):
        mock_fetch.return_value = {
            "url": "https://orange.biolab.si",
            "status": 200,
            "title": "Orange Data Mining",
            "text": "Welcome to Orange",
            "links": ["https://orange.biolab.si/download"],
            "raw_html": "<html><title>Orange Data Mining</title><body>Welcome to Orange</body></html>",
        }

        self.widget.url = "https://orange.biolab.si"
        self.widget.commit()

        out_data = self.get_output(self.widget.Outputs.data)
        out_text = self.get_output(self.widget.Outputs.text)

        self.assertIsNotNone(out_data)
        self.assertEqual(len(out_data), 1)
        self.assertIn("Welcome to Orange", out_text)
        self.assertFalse(self.widget.Error.crawl_error.is_active())

    def test_missing_url_error(self):
        self.widget.url = ""
        self.widget.commit()

        out_data = self.get_output(self.widget.Outputs.data)
        out_text = self.get_output(self.widget.Outputs.text)

        self.assertIsNone(out_data)
        self.assertIsNone(out_text)
        self.assertTrue(self.widget.Error.crawl_error.is_active())
