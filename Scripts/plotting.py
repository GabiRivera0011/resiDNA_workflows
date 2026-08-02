"""Shared table styling used by both the Phase I notebook and the Streamlit app."""


def style_table(data, caption="", hide_index=True, precision=2, align="center",
                 highlight_rows=None, highlight_color="#D4EDDA", precision_overrides=None):
    """Presentation-ready styling for tables — used by both the notebook and app.py
    so their tables (and the PDF report) look identical. Colors are explicit so
    tables render in light mode regardless of the editor/notebook theme.
    """
    styler = data.style.set_caption(caption)

    if highlight_rows is not None:
        def _highlight(row):
            if highlight_rows.loc[row.name]:
                return [f"background-color: {highlight_color} !important"] * len(row)
            return [""] * len(row)
        styler = styler.apply(_highlight, axis=1)

    if hide_index:
        styler = styler.hide(axis="index")

    styler = styler.format(precision=precision, na_rep="—")

    # Per-column precision overrides (e.g. Total DNA / Protein Concentration / DNA per
    # Protein always render at 4 decimals, regardless of this table's default precision)
    if precision_overrides:
        for col, col_precision in precision_overrides.items():
            if col in data.columns:
                styler = styler.format(precision=col_precision, na_rep="—", subset=[col])

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
