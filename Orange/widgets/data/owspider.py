import re
import urllib.request
import urllib.error
import urllib.parse
from html.parser import HTMLParser
from typing import Optional, List, Dict, Any

from AnyQt.QtCore import Qt

from Orange.data import Table, Domain, StringVariable, ContinuousVariable
from Orange.widgets import gui
from Orange.widgets.settings import Setting
from Orange.widgets.widget import OWWidget, Input, Output, Msg


class SimpleHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.in_title = False
        self.text_parts = []
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "title":
            self.in_title = True
        elif tag.lower() == "a":
            for attr, value in attrs:
                if attr.lower() == "href" and value:
                    self.links.append(value)

    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        cleaned = data.strip()
        if cleaned:
            self.text_parts.append(cleaned)

    def get_text(self) -> str:
        return " ".join(self.text_parts)


def fetch_url(url: str, user_agent: str = "Mozilla/5.0", timeout: int = 10) -> Dict[str, Any]:
    url = url.strip()
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "http://" + url

    headers = {"User-Agent": user_agent}
    req = urllib.request.Request(url, headers=headers)

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        status_code = resp.status
        content_type = resp.headers.get_content_type()
        raw_data = resp.read()

        charset = resp.headers.get_param("charset") or "utf-8"
        try:
            html_text = raw_data.decode(charset, errors="replace")
        except Exception:
            html_text = raw_data.decode("utf-8", errors="replace")

    parser = SimpleHTMLParser()
    parser.feed(html_text)

    # Resolve relative links
    base_url = url
    resolved_links = []
    for link in parser.links:
        resolved = urllib.parse.urljoin(base_url, link)
        if resolved.startswith("http://") or resolved.startswith("https://"):
            resolved_links.append(resolved)

    return {
        "url": url,
        "status": status_code,
        "title": parser.title.strip(),
        "text": parser.get_text(),
        "links": resolved_links,
        "raw_html": html_text,
    }


class OWSpider(OWWidget):
    name = "Spider"
    description = "Crawl and extract text / data from web pages."
    category = "Data"
    icon = "icons/PythonScript.svg"
    priority = 3170
    keywords = "spider, crawl, web, scraper, url, html, text, fetch"

    class Inputs:
        url_input = Input("URL", object, auto_summary=False)

    class Outputs:
        data = Output("Data", Table, auto_summary=False)
        text = Output("Text", object, auto_summary=False)

    # Settings
    url = Setting("https://orange.biolab.si")
    max_depth = Setting(1)
    max_pages = Setting(5)
    timeout = Setting(10)
    user_agent = Setting("Mozilla/5.0 (Windows NT 10.0; Win64; x64) Orange3-Spider/1.0")

    class Error(OWWidget.Error):
        crawl_error = Msg("Spider Error: {}")

    def __init__(self):
        super().__init__()

        self.input_url: Optional[Any] = None

        # GUI Layout
        form_box = gui.vBox(self.controlArea, "Spider Settings")

        gui.lineEdit(
            form_box, self, "url", "Target URL:",
            orientation=Qt.Horizontal,
            tooltip="Web page URL to crawl."
        )

        gui.spin(
            form_box, self, "max_depth", 1, 10, step=1,
            label="Max Depth:",
            tooltip="Maximum crawl depth for following links."
        )

        gui.spin(
            form_box, self, "max_pages", 1, 100, step=1,
            label="Max Pages:",
            tooltip="Maximum number of pages to crawl."
        )

        gui.spin(
            form_box, self, "timeout", 1, 60, step=1,
            label="Timeout (s):",
            tooltip="HTTP request timeout in seconds."
        )

        gui.lineEdit(
            form_box, self, "user_agent", "User-Agent:",
            orientation=Qt.Horizontal,
            tooltip="User-Agent header for HTTP requests."
        )

        gui.button(self.controlArea, self, "Crawl", callback=self.commit)

        # Output Preview
        self.result_box = gui.vBox(self.mainArea, "Crawl Results")
        self.result_label = gui.widgetLabel(self.result_box, "No results yet.")

    @Inputs.url_input
    def set_url_input(self, url_data):
        self.input_url = url_data

    def handleNewSignals(self):
        self.commit()

    def _get_start_urls(self) -> List[str]:
        if self.input_url is not None:
            if isinstance(self.input_url, Table):
                urls = []
                for row in self.input_url:
                    for val in row:
                        val_str = str(val).strip()
                        if val_str.startswith("http://") or val_str.startswith("https://"):
                            urls.append(val_str)
                if urls:
                    return urls
            else:
                input_str = str(self.input_url).strip()
                if input_str:
                    return [input_str]

        start_url = self.url.strip()
        return [start_url] if start_url else []

    def commit(self):
        self.Error.clear()

        start_urls = self._get_start_urls()
        if not start_urls:
            self.Error.crawl_error("Please enter a valid target URL.")
            self.result_label.setText("Error: Missing target URL.")
            self.Outputs.data.send(None)
            self.Outputs.text.send(None)
            return

        visited = set()
        crawled_results = []
        queue = [(u, 1) for u in start_urls]

        try:
            while queue and len(crawled_results) < self.max_pages:
                current_url, depth = queue.pop(0)
                if current_url in visited:
                    continue
                visited.add(current_url)

                try:
                    res = fetch_url(current_url, user_agent=self.user_agent, timeout=self.timeout)
                    crawled_results.append(res)

                    if depth < self.max_depth:
                        for link in res["links"]:
                            if link not in visited and len(crawled_results) + len(queue) < self.max_pages:
                                queue.append((link, depth + 1))
                except Exception as page_err:
                    # Skip un-fetchable pages
                    continue

            if not crawled_results:
                raise ValueError("Failed to crawl any pages.")

            # Build Orange Table
            var_url = StringVariable("URL")
            var_title = StringVariable("Title")
            var_status = ContinuousVariable("Status")
            var_text = StringVariable("Content Text")

            domain = Domain([var_status], metas=[var_url, var_title, var_text])

            X = []
            metas = []
            text_outputs = []

            for r in crawled_results:
                X.append([r["status"]])
                metas.append([r["url"], r["title"], r["text"]])
                text_outputs.append(f"=== {r['title']} ({r['url']}) ===\n{r['text']}")

            out_table = Table.from_numpy(domain, X=X, metas=metas)
            combined_text = "\n\n".join(text_outputs)

            self.result_label.setText(
                f"Crawled {len(crawled_results)} page(s).\n\n" +
                (combined_text[:500] + ("..." if len(combined_text) > 500 else ""))
            )

            self.Outputs.data.send(out_table)
            self.Outputs.text.send(combined_text)

        except Exception as e:
            self.Error.crawl_error(str(e))
            self.result_label.setText(f"Error: {e}")
            self.Outputs.data.send(None)
            self.Outputs.text.send(None)


if __name__ == "__main__":  # pragma: no cover
    from Orange.widgets.utils.widgetpreview import WidgetPreview
    WidgetPreview(OWSpider).run()
