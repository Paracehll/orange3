import concurrent.futures
import json
import urllib.request
import urllib.error
from typing import Optional, List, Dict, Any

from AnyQt.QtCore import Qt

from Orange.widgets import gui
from Orange.widgets.settings import Setting
from Orange.widgets.widget import OWWidget, Input, Output, Msg


PROVIDERS = ["Auto / OpenAI", "DeepSeek", "Gemini", "NVIDIA NIM"]
DEFAULT_NVIDIA_MODEL = "meta/llama-3.1-8b-instruct"


def fetch_nvidia_models(api_key: str) -> List[str]:
    """
    Fetch available models from NVIDIA NIM API.
    """
    api_key = api_key.strip()
    if not api_key:
        return [DEFAULT_NVIDIA_MODEL]

    url = "https://integrate.api.nvidia.com/v1/models"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [item["id"] for item in data.get("data", []) if "id" in item]
            if models:
                return sorted(models)
    except Exception:
        pass

    return [DEFAULT_NVIDIA_MODEL]


def detect_provider(key: str, selected_provider: int) -> str:
    if selected_provider == 1:
        return "deepseek"
    elif selected_provider == 2:
        return "gemini"
    elif selected_provider == 3:
        return "nvidia"

    # Auto-detection mode (selected_provider == 0)
    key_strip = key.strip()
    if key_strip.startswith("nvapi-"):
        return "nvidia"
    elif key_strip.startswith("AIza"):
        return "gemini"
    elif "deepseek" in key_strip.lower():
        return "deepseek"
    return "openai"


def call_llm_api(prompt_text: str, api_key: str, provider: str = "openai", model_name: str = "") -> str:
    """
    Call LLM provider API (OpenAI, DeepSeek, Gemini, NVIDIA NIM).
    """
    api_key = api_key.strip()
    headers = {
        "Content-Type": "application/json",
    }

    if provider == "openai":
        url = "https://api.openai.com/v1/chat/completions"
        headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": model_name or "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt_text}]
        }
    elif provider == "deepseek":
        url = "https://api.deepseek.com/v1/chat/completions"
        headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": model_name or "deepseek-chat",
            "messages": [{"role": "user", "content": prompt_text}]
        }
    elif provider == "gemini":
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt_text}]}]
        }
    elif provider == "nvidia":
        url = "https://integrate.api.nvidia.com/v1/chat/completions"
        headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": model_name or DEFAULT_NVIDIA_MODEL,
            "messages": [{"role": "user", "content": prompt_text}]
        }
    else:
        raise ValueError(f"Unsupported provider: {provider}")

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    with urllib.request.urlopen(req, timeout=60) as resp:
        response_data = json.loads(resp.read().decode("utf-8"))

    if provider in ("openai", "deepseek", "nvidia"):
        return response_data["choices"][0]["message"]["content"]
    elif provider == "gemini":
        return response_data["candidates"][0]["content"]["parts"][0]["text"]

    return str(response_data)


def execute_llm_task(
    prompt_text: str,
    api_keys: List[str],
    provider_idx: int = 0,
    retry: bool = True,
    model_name: str = ""
) -> str:
    """
    Execute task with optional key rotation / retry.
    """
    if not api_keys:
        raise ValueError("No API key provided.")

    last_error = None
    for key in api_keys:
        key = key.strip()
        if not key:
            continue

        provider = detect_provider(key, provider_idx)

        try:
            return call_llm_api(prompt_text, key, provider=provider, model_name=model_name)
        except Exception as e:
            last_error = e
            if not retry:
                raise e

    if last_error:
        raise last_error
    raise ValueError("Execution failed: No valid API keys.")


class OWLLM(OWWidget):
    name = "LLM"
    description = "Process inputs using LLM with parallel execution and API key retry."
    category = "Data"
    icon = "icons/PythonScript.svg"
    priority = 3160
    keywords = "llm, gpt, openai, deepseek, gemini, nvidia, chatgpt, prompt, ai"

    class Inputs:
        prompt = Input("Prompt", object, auto_summary=False)
        skill = Input("Skill", object, auto_summary=False)
        file = Input("File", object, auto_summary=False)

    class Outputs:
        result = Output("Result", object, auto_summary=False)

    # Settings
    api_key = Setting("")
    provider_idx = Setting(0)
    model_idx = Setting(0)
    parallel_count = Setting(1)
    retry = Setting(True)

    class Error(OWWidget.Error):
        api_error = Msg("LLM Execution Error: {}")

    def __init__(self):
        super().__init__()

        self.input_prompt: Optional[Any] = None
        self.input_skill: Optional[Any] = None
        self.input_file: Optional[Any] = None
        self.result_data: Optional[Any] = None
        self.nvidia_models: List[str] = [DEFAULT_NVIDIA_MODEL]

        # GUI Layout
        form_box = gui.vBox(self.controlArea, "LLM Settings")

        gui.comboBox(
            form_box, self, "provider_idx",
            items=PROVIDERS,
            label="Provider:",
            callback=self._on_provider_or_key_changed,
            tooltip="Select LLM provider or auto-detect from API Key format."
        )

        gui.lineEdit(
            form_box, self, "api_key", "API Key(s) (comma-separated):",
            orientation=Qt.Horizontal,
            callback=self._on_provider_or_key_changed,
            tooltip="Supported: OpenAI (ChatGPT), DeepSeek, Gemini, NVIDIA NIM. Separate multiple keys with commas."
        )

        self.model_combo = gui.comboBox(
            form_box, self, "model_idx",
            items=self.nvidia_models,
            label="NVIDIA Model:",
            tooltip="Select model for NVIDIA NIM provider."
        )

        gui.spin(
            form_box, self, "parallel_count", 1, 64, step=1,
            label="Parallel Count:",
            tooltip="Number of parallel instances to process split file contents."
        )

        gui.checkBox(
            form_box, self, "retry", "Retry with next API key on failure",
            tooltip="Automatically switch to the next API key if an error occurs."
        )

        gui.button(self.controlArea, self, "Run", callback=self.commit)

        # Output / Status Box
        self.result_box = gui.vBox(self.mainArea, "Result Preview")
        self.result_label = gui.widgetLabel(self.result_box, "No result yet.")

        self._update_model_combobox()

    def _on_provider_or_key_changed(self):
        self._update_model_combobox()

    def _update_model_combobox(self):
        keys = [k.strip() for k in self.api_key.split(",") if k.strip()]
        first_key = keys[0] if keys else ""
        provider = detect_provider(first_key, self.provider_idx)

        if provider == "nvidia" and first_key:
            fetched_models = fetch_nvidia_models(first_key)
            if fetched_models:
                self.nvidia_models = fetched_models

        self.model_combo.clear()
        self.model_combo.addItems(self.nvidia_models)

        if self.model_idx >= len(self.nvidia_models):
            self.model_idx = 0
        self.model_combo.setCurrentIndex(self.model_idx)

    @Inputs.prompt
    def set_prompt(self, prompt):
        self.input_prompt = prompt

    @Inputs.skill
    def set_skill(self, skill):
        self.input_skill = skill

    @Inputs.file
    def set_file(self, file_data):
        self.input_file = file_data

    def handleNewSignals(self):
        self.commit()

    def _split_content(self, file_data: Any, n: int) -> List[str]:
        if file_data is None:
            return [""]

        text = str(file_data)
        if n <= 1 or not text:
            return [text]

        lines = text.splitlines(keepends=True)
        if not lines:
            return [text]

        chunk_size = max(1, (len(lines) + n - 1) // n)
        chunks = []
        for i in range(0, len(lines), chunk_size):
            chunks.append("".join(lines[i:i + chunk_size]))
        return chunks

    def commit(self):
        self.Error.clear()

        keys = [k.strip() for k in self.api_key.split(",") if k.strip()]
        if not keys:
            self.Error.api_error("Please enter at least one API key.")
            self.result_label.setText("Error: Missing API key.")
            self.Outputs.result.send(None)
            return

        prompt_str = str(self.input_prompt) if self.input_prompt is not None else ""
        skill_str = str(self.input_skill) if self.input_skill is not None else ""

        selected_model = ""
        if 0 <= self.model_idx < len(self.nvidia_models):
            selected_model = self.nvidia_models[self.model_idx]

        file_chunks = self._split_content(self.input_file, self.parallel_count)

        tasks = []
        for chunk in file_chunks:
            full_prompt_parts = []
            if skill_str:
                full_prompt_parts.append(f"[Skill/Instruction]\n{skill_str}")
            if prompt_str:
                full_prompt_parts.append(f"[Prompt]\n{prompt_str}")
            if chunk:
                full_prompt_parts.append(f"[Content]\n{chunk}")

            tasks.append("\n\n".join(full_prompt_parts))

        results = []
        try:
            if len(tasks) == 1 or self.parallel_count <= 1:
                for task_prompt in tasks:
                    res = execute_llm_task(
                        task_prompt,
                        keys,
                        provider_idx=self.provider_idx,
                        retry=self.retry,
                        model_name=selected_model
                    )
                    results.append(res)
            else:
                with concurrent.futures.ThreadPoolExecutor(max_workers=self.parallel_count) as executor:
                    futures = [
                        executor.submit(
                            execute_llm_task,
                            t,
                            keys,
                            self.provider_idx,
                            self.retry,
                            selected_model
                        )
                        for t in tasks
                    ]
                    # Preserve chunk order
                    results = [f.result() for f in futures]

            final_result = "\n\n".join(results) if len(results) > 1 else (results[0] if results else "")
            self.result_data = final_result
            self.result_label.setText(final_result[:500] + ("..." if len(final_result) > 500 else ""))
            self.Outputs.result.send(final_result)

        except Exception as e:
            self.Error.api_error(str(e))
            self.result_label.setText(f"Error: {e}")
            self.Outputs.result.send(None)


if __name__ == "__main__":  # pragma: no cover
    from Orange.widgets.utils.widgetpreview import WidgetPreview
    WidgetPreview(OWLLM).run()
