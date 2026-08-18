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


class RerunTriggered(Exception):
    """Raised by the fake st.rerun() — real st.rerun() never returns either,
    it immediately restarts the script from the top. Distinct from StopExec
    so a test can tell "the app asked to rerun" apart from "the app called
    st.stop() over missing columns"."""


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
        self.warnings = []
        # Real st.session_state is a MutableMapping-like object; a plain dict
        # supports every access pattern this app uses (.get(), .pop(), [key]).
        self.session_state = {}
        # Which button labels should report as clicked this run — tests can
        # populate before calling run_app(); everything else defaults to
        # "not clicked" (False), matching a real headless/no-interaction run.
        self._button_clicks = set()

    def set_page_config(self, **kw): pass
    def title(self, *a, **kw): pass
    def header(self, *a, **kw): pass
    def subheader(self, *a, **kw): pass
    def markdown(self, *a, **kw): pass
    def divider(self, *a, **kw): pass
    def text_input(self, *a, **kw): return ""
    def number_input(self, *a, **kw): return kw.get("value")
    def success(self, *a, **kw): pass
    def error(self, *a, **kw): pass
    def caption(self, *a, **kw): pass
    def warning(self, *a, **kw): self.warnings.append(a)
    def columns(self, n, *a, **kw): return [nullcontext() for _ in range(n)]
    def plotly_chart(self, *a, **kw): pass
    def download_button(self, *a, **kw):
        label = a[0] if a else kw.get("label")
        return label in self._button_clicks
    def table(self, data, *a, **kw): self.tables.append(data)
    def file_uploader(self, *a, **kw): return self._uploaded
    def stop(self): raise StopExec()
    def button(self, label, *a, **kw): return label in self._button_clicks
    def dialog(self, *a, **kw): return lambda f: f
    def rerun(self): raise RerunTriggered()


def run_app(repo_root, data_path, session_state=None, button_clicks=None):
    """Execute the real app/app.py against `data_path` as if it were an
    uploaded file, and return the resulting module namespace (so a test can
    inspect final_results / reportable_results / etc. directly). Raises
    StopExec if the app itself calls st.stop() (e.g. missing required columns).

    `session_state`, if given, seeds the fake st.session_state before the app
    runs — e.g. {"criteria_override_SAMPLE_QTY_CV_MAX": 20.0} to simulate the
    Edit Acceptance Criteria dialog having been used.

    `button_clicks`, if given, is an iterable of button labels that should
    report as clicked this run (e.g. ["Download PDF Report"]) — every other
    button defaults to "not clicked".

    The returned namespace's `ns["st"]` is the same FakeStreamlit instance
    used for the run, so a test can also inspect what it recorded
    (ns["st"].warnings, ns["st"].tables).
    """
    import sys

    fake_st = FakeStreamlit()
    fake_st._uploaded = FakeUploadedFile(data_path)
    if session_state:
        fake_st.session_state = dict(session_state)
    if button_clicks:
        fake_st._button_clicks = set(button_clicks)
    sys.modules["streamlit"] = fake_st

    app_path = repo_root / "app" / "app.py"
    src = app_path.read_text()
    ns = {"__name__": "__main__", "__file__": str(app_path)}
    exec(compile(src, str(app_path), "exec"), ns)
    return ns
