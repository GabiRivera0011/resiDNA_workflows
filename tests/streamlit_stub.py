"""A minimal fake `streamlit` module so app/app.py's top-level script can be
exec'd headlessly in a test, without a running Streamlit server or browser.

Widgets return harmless defaults (empty text inputs, no-op charts/tables);
`file_uploader` returns whatever FakeUploadedFile was primed via `_uploaded`.
"""
import io
import types
from contextlib import nullcontext
from pathlib import Path


class StopExec(Exception):
    """Raised by the fake st.stop() so a test can distinguish "the app itself
    called st.stop()" (e.g. a file missing required columns) from a real error."""


class FakeUploadedFile(io.BytesIO):
    def __init__(self, path):
        with open(path, "rb") as f:
            data = f.read()
        super().__init__(data)
        self.name = Path(path).name


class FakeStreamlit(types.ModuleType):
    def __init__(self):
        super().__init__("streamlit")
        self._uploaded = None
        self.tables = []

    def set_page_config(self, **kw): pass
    def title(self, *a, **kw): pass
    def header(self, *a, **kw): pass
    def text_input(self, *a, **kw): return ""
    def success(self, *a, **kw): pass
    def error(self, *a, **kw): pass
    def caption(self, *a, **kw): pass
    def warning(self, *a, **kw): pass
    def columns(self, n, *a, **kw): return [nullcontext() for _ in range(n)]
    def plotly_chart(self, *a, **kw): pass
    def download_button(self, *a, **kw): pass
    def table(self, data, *a, **kw): self.tables.append(data)
    def file_uploader(self, *a, **kw): return self._uploaded
    def stop(self): raise StopExec()


def run_app(repo_root, data_path):
    """Execute the real app/app.py against `data_path` as if it were an
    uploaded file, and return the resulting module namespace (so a test can
    inspect final_results / reportable_results / etc. directly). Raises
    StopExec if the app itself calls st.stop() (e.g. missing required columns)."""
    import sys

    fake_st = FakeStreamlit()
    fake_st._uploaded = FakeUploadedFile(data_path)
    sys.modules["streamlit"] = fake_st

    app_path = repo_root / "app" / "app.py"
    src = app_path.read_text()
    ns = {"__name__": "__main__", "__file__": str(app_path)}
    exec(compile(src, str(app_path), "exec"), ns)
    return ns
