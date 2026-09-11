from dash import dcc, html
from dash.dash_table.Format import Format, Scheme

from load import load_picks
from ui import MUTED, csv_columns, table


def tab():
    rows = load_picks()
    cols = csv_columns(rows)
    pct = Format(precision=1, scheme=Scheme.percentage)
    num = Format(precision=2)
    for col in cols:
        if col["id"] in ("home_win_prob", "decision_prob", "p_over_honest", "p_over"):
            col["type"] = "numeric"
            col["format"] = pct
        elif col["id"] in ("spread_line", "pred_margin", "pred_margin_scaled"):
            col["type"] = "numeric"
            col["format"] = num
    return dcc.Tab(
        label="Picks",
        value="picks",
        children=[
            html.P("2026 · Week 1", style={"color": MUTED, "marginTop": 16}),
            table(rows, cols),
        ],
    )
