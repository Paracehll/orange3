from unittest.mock import patch
from Orange.data import Table, Domain, StringVariable, ContinuousVariable
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

    @patch("Orange.widgets.data.owspider.fetch_url")
    def test_table_tasks_input(self, mock_fetch):
        mock_fetch.return_value = {
            "url": "https://example.com",
            "status": 200,
            "title": "Example",
            "text": "Example Domain",
            "links": [],
            "raw_html": "<html></html>",
        }

        domain = Domain(
            [ContinuousVariable("max depth"), ContinuousVariable("max pages"), ContinuousVariable("timeout")],
            metas=[StringVariable("url")]
        )
        task_table = Table.from_numpy(domain, X=[[2, 10, 15]], metas=[["https://example.com"]])

        self.send_signal(self.widget.Inputs.data_input, task_table)

        out_data = self.get_output(self.widget.Outputs.data)
        out_text = self.get_output(self.widget.Outputs.text)

        self.assertIsNotNone(out_data)
        self.assertIn("Example Domain", out_text)

    def test_missing_url_error(self):
        self.widget.url = ""
        self.widget.commit()

        out_data = self.get_output(self.widget.Outputs.data)
        out_text = self.get_output(self.widget.Outputs.text)

        self.assertIsNone(out_data)
        self.assertIsNone(out_text)
        self.assertTrue(self.widget.Error.crawl_error.is_active())
