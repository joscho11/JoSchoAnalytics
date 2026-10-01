import numpy as np
import pandas as pd
import plotly.graph_objects as go

from league_insights_view import _phone_round_heatmap


def test_phone_round_heatmap_keeps_all_sixteen_rounds():
    rounds = list(range(1, 17))
    positions = ["QB", "RB", "WR", "TE", "K"]
    values = np.arange(1, len(positions) * len(rounds) + 1).reshape(len(positions), len(rounds))
    frame = pd.DataFrame(values, index=positions, columns=rounds)
    desktop = go.Figure(go.Heatmap(
        z=frame.values,
        x=frame.columns.tolist(),
        y=frame.index.tolist(),
        text=[[f"{value:.1f}" for value in row] for row in frame.values],
        texttemplate="%{text}",
    ))
    desktop.update_layout(margin=dict(l=55, r=20, t=55, b=45))

    phone = _phone_round_heatmap(desktop, len(rounds))

    assert list(phone.data[0].x) == rounds
    assert list(phone.data[0].y) == positions
    desktop_trace = desktop.to_dict()["data"][0]
    phone_trace = phone.to_dict()["data"][0]
    assert phone_trace["z"] == desktop_trace["z"]
    assert phone.data[0].text == desktop.data[0].text
    assert phone.layout.width == 55 + 20 + 44 * 16 + 90
    assert phone.layout.autosize is False
    assert desktop.layout.width is None
