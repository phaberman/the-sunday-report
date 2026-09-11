from dash import dash_table

BG = "#f7f7f5"
FG = "#1c1c1c"
MUTED = "#5c5c5c"
LINE = "#e2e2dc"
HEADER = "#f0f0eb"
ACCENT = "#1a3a2a"


def csv_columns(rows):
    return [{"name": k, "id": k} for k in rows[0]] if rows else []


def table(data, columns):
    return dash_table.DataTable(
        data=data,
        columns=columns,
        sort_action="native",
        page_size=20,
        style_table={"overflowX": "auto"},
        style_header={
            "backgroundColor": HEADER,
            "color": ACCENT,
            "fontWeight": "600",
            "border": f"1px solid {LINE}",
            "fontFamily": "system-ui, sans-serif",
        },
        style_cell={
            "backgroundColor": "#fff",
            "color": FG,
            "border": f"1px solid {LINE}",
            "padding": "10px 12px",
            "fontFamily": "system-ui, sans-serif",
            "fontSize": "14px",
        },
    )
