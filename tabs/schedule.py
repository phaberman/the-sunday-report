from dash import dcc, html

from load import load_schedule
from ui import MUTED, csv_columns, table


def tab():
    rows = load_schedule()
    return dcc.Tab(
        label="Schedule",
        value="schedule",
        children=[
            html.P("2026", style={"color": MUTED, "marginTop": 16}),
            table(rows, csv_columns(rows)),
        ],
    )
