from dash import dcc, html
from dash.dash_table.Format import Format, Scheme

from load import load_picks
from ui import MUTED, csv_columns, table


def tab():
    rows = load_picks()
    cols = csv_columns(rows)
    if rows:
        pct = Format(precision=1, scheme=Scheme.percentage)
        for col in cols:
            if col["id"] in ("home_win_prob", "clf_win_prob"):
                col["type"] = "numeric"
                col["format"] = pct
            elif col["id"] == "pred_margin":
                col["type"] = "numeric"
                col["format"] = Format(precision=1)
    week = rows[0]["week"] if rows else "?"
    season = rows[0]["season"] if rows else "?"
    return dcc.Tab(
        label="Picks",
        value="picks",
        children=[
            html.P(f"{season} · Week {week}", style={"color": MUTED, "marginTop": 16}),
            table(rows, cols, highlight_pick=True),
        ],
    )
