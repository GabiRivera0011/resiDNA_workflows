"""Shared table styling used by both the Phase I notebook and the Streamlit app."""

import pandas as pd


def format_value(value, precision):
    """Render a single cell value as a display string: NaN -> em dash, numeric ->
    fixed precision, everything else -> str(). Shared with app.py's PDF builder so
    on-screen and PDF numbers always agree.
    """
    if pd.isna(value):
        return "—"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:.{precision}f}"
    return str(value)


def format_df_for_display(data, precision=2, precision_overrides=None):
    """Format every cell to its final display string (see format_value).

    Used by style_table() below to pre-format values to strings before they ever
    reach a Styler — st.table() (unlike Jupyter) rebuilds its own HTML from the
    Styler's underlying data rather than rendering its CSS, and right-aligns any
    column that's still numeric dtype regardless of the Styler's own text-align
    rules. Formatting to strings first removes that numeric signal, so every column
    renders with the alignment style_table() actually asked for.
    """
    precision_overrides = precision_overrides or {}
    formatted = data.copy()
    for col in formatted.columns:
        col_precision = precision_overrides.get(col, precision)
        formatted[col] = formatted[col].apply(lambda v: format_value(v, col_precision))
    return formatted


def style_table(data, caption="", hide_index=True, precision=2, align="center",
                 highlight_rows=None, highlight_color="#D4EDDA", precision_overrides=None):
    """Presentation-ready styling for tables — used by both the notebook and app.py
    so their tables (and the PDF report) look identical. Colors are explicit so
    tables render in light mode regardless of the editor/notebook theme.
    """
    formatted = format_df_for_display(data, precision=precision, precision_overrides=precision_overrides)
    styler = formatted.style.set_caption(caption)

    if highlight_rows is not None:
        def _highlight(row):
            if highlight_rows.loc[row.name]:
                return [f"background-color: {highlight_color} !important"] * len(row)
            return [""] * len(row)
        styler = styler.apply(_highlight, axis=1)

    if hide_index:
        styler = styler.hide(axis="index")

    styler = styler.set_table_attributes(
        'style="background-color:#FFFFFF; border-collapse:collapse;"'
    )
    styler = styler.set_table_styles([
        {"selector": "caption", "props": [
            ("caption-side", "top"), ("font-size", "13pt"), ("font-weight", "bold"),
            ("text-align", "left"), ("padding", "4px 0 8px 0"),
            ("color", "#2C3E50"), ("background-color", "#FFFFFF"),
        ]},
        {"selector": "th", "props": [
            ("background-color", "#2C3E50"), ("color", "#FFFFFF"), ("font-weight", "bold"),
            ("text-align", align), ("padding", "6px 12px"), ("border", "1px solid #2C3E50"),
        ]},
        {"selector": "td", "props": [
            ("padding", "6px 12px"), ("border", "1px solid #DDDDDD"),
            ("text-align", align), ("color", "#2C2C2C"), ("background-color", "#FFFFFF"),
        ]},
        {"selector": "tr:nth-child(even) td", "props": [("background-color", "#F7F9FA")]},
    ])
    return styler
