import re
import urllib.request
import urllib.error
import urllib.parse
from html.parser import HTMLParser
from typing import Optional, List, Dict, Any, Tuple

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
        data_input = Input("Data", object, auto_summary=False)

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

        self.input_data: Optional[Any] = None

        # GUI Layout
        form_box = gui.vBox(self.controlArea, "Spider Settings")

        gui.lineEdit(
            form_box, self, "url", "Target URL:",
            orientation=Qt.Horizontal,
            tooltip="Default web page URL to crawl when no input table is connected."
        )

        gui.spin(
            form_box, self, "max_depth", 1, 10, step=1,
            label="Max Depth:",
            tooltip="Maximum crawl depth for following links."
        )

        gui.spin(
            form_box, self, "max_pages", 1, 100, step=1,
            label="Max Pages:",
            tooltip="Maximum number of pages to crawl per task."
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

    @Inputs.data_input
    def set_data_input(self, data):
        self.input_data = data

    def handleNewSignals(self):
        self.commit()

    def _parse_tasks(self) -> List[Tuple[str, int, int, int]]:
        """
        Parse tasks from input data table or default settings.
        Returns list of (url, max_depth, max_pages, timeout).
        """
        tasks = []
        if self.input_data is not None and isinstance(self.input_data, Table):
            table = self.input_data
            domain = table.domain

            # Map column names (case-insensitive & space/underscore insensitive)
            col_map = {}
            all_vars = domain.attributes + domain.class_vars + domain.metas
            for var in all_vars:
                norm_name = re.sub(r"[\s_]+", "", var.name.lower())
                col_map[norm_name] = var

            url_var = col_map.get("url")
            depth_var = col_map.get("maxdepth")
            pages_var = col_map.get("maxpages")
            timeout_var = col_map.get("timeout")

            for row in table:
                task_url = str(row[url_var]).strip() if url_var is not None else ""
                if not task_url:
                    # Fallback to searching first URL-like string in row
                    for val in row:
                        val_str = str(val).strip()
                        if val_str.startswith("http://") or val_str.startswith("https://"):
                            task_url = val_str
                            break

                if not task_url:
                    continue

                try:
                    task_depth = int(float(row[depth_var])) if depth_var is not None else self.max_depth
                except (ValueError, TypeError):
                    task_depth = self.max_depth

                try:
                    task_pages = int(float(row[pages_var])) if pages_var is not None else self.max_pages
                except (ValueError, TypeError):
                    task_pages = self.max_pages

                try:
                    task_timeout = int(float(row[timeout_var])) if timeout_var is not None else self.timeout
                except (ValueError, TypeError):
                    task_timeout = self.timeout

                tasks.append((task_url, task_depth, task_pages, task_timeout))

        if not tasks:
            # Fallback to GUI settings
            default_url = self.url.strip()
            if default_url:
                tasks.append((default_url, self.max_depth, self.max_pages, self.timeout))

        return tasks

    def commit(self):
        self.Error.clear()

        tasks = self._parse_tasks()
        if not tasks:
            self.Error.crawl_error("Please enter a valid target URL or connect a task table.")
            self.Outputs.data.send(None)
            self.Outputs.text.send(None)
            return

        all_crawled_results = []
        try:
            for task_url, task_depth, task_pages, task_timeout in tasks:
                visited = set()
                queue = [(task_url, 1)]
                task_results_count = 0

                while queue and task_results_count < task_pages:
                    current_url, depth = queue.pop(0)
                    if current_url in visited:
                        continue
                    visited.add(current_url)

                    try:
                        res = fetch_url(current_url, user_agent=self.user_agent, timeout=task_timeout)
                        all_crawled_results.append(res)
                        task_results_count += 1

                        if depth < task_depth:
                            for link in res["links"]:
                                if link not in visited and task_results_count + len(queue) < task_pages:
                                    queue.append((link, depth + 1))
                    except Exception:
                        continue

            if not all_crawled_results:
                raise ValueError("Failed to crawl any pages.")

            # Build Orange Table Output
            var_url = StringVariable("URL")
            var_title = StringVariable("Title")
            var_status = ContinuousVariable("Status")
            var_text = StringVariable("Content Text")

            domain = Domain([var_status], metas=[var_url, var_title, var_text])

            X = []
            metas = []
            text_outputs = []

            for r in all_crawled_results:
                X.append([r["status"]])
                metas.append([r["url"], r["title"], r["text"]])
                text_outputs.append(f"=== {r['title']} ({r['url']}) ===\n{r['text']}")

            out_table = Table.from_numpy(domain, X=X, metas=metas)
            combined_text = "\n\n".join(text_outputs)

            self.Outputs.data.send(out_table)
            self.Outputs.text.send(combined_text)

        except Exception as e:
            self.Error.crawl_error(str(e))
            self.Outputs.data.send(None)
            self.Outputs.text.send(None)


if __name__ == "__main__":  # pragma: no cover
    from Orange.widgets.utils.widgetpreview import WidgetPreview
    WidgetPreview(OWSpider).run()
