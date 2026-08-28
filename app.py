from dash import Dash, dcc, html

from tabs import TABS
from ui import ACCENT, BG, FG, HEADER, LINE

app = Dash(__name__)
app.layout = html.Div(
    style={
        "background": BG,
        "color": FG,
        "fontFamily": "Georgia, 'Times New Roman', serif",
        "minHeight": "100vh",
        "padding": "40px 48px",
        "maxWidth": "1400px",
        "margin": "0 auto",
    },
    children=[
        html.H1("The Sunday Report", style={"color": ACCENT, "marginBottom": 0, "fontWeight": "600"}),
        dcc.Tabs(
            value="picks",
            colors={"border": LINE, "primary": ACCENT, "background": HEADER},
            children=TABS,
        ),
    ],
)

if __name__ == "__main__":
    app.run(debug=True)
