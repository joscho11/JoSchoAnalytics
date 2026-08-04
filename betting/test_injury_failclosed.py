"""Identity failures must ABORT prediction, never become zero features.

`_build_injuries` wraps its whole body in `except Exception -> zeros`. That fallback is
legitimate for an unavailable injury FEED (no report ≈ no known injuries). It is NOT
legitimate for an identity failure: ambiguous matches, a merge that fanned out, or a
violated invariant would silently ship a wrong `diff_active_allpro_weighted`
(PROD_FEATURES_35 #11) instead of refusing to predict.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

_B = Path(__file__).resolve().parent
if str(_B) not in sys.path:
    sys.path.insert(0, str(_B))

import features as F  # noqa: E402
from allpro_identity import AllProIdentityError  # noqa: E402


def _colliding_allpro():
    """Two DIFFERENT players sharing a name on two teams in one year, unreviewed."""
    return pd.DataFrame([
        {"Pos": "LB", "Player": "Unresolved Twin", "Team": "KC", "Year": 2024,
         "Side": "defense"},
        {"Pos": "LB", "Player": "Unresolved Twin", "Team": "SF", "Year": 2024,
         "Side": "defense"},
    ])


def test_identity_collision_raises_through_the_public_serving_builder():
    """Injected through `_build_allpro`, which `build_features` calls on the live path."""
    upcoming = pd.DataFrame([{"home_team": "KC", "away_team": "SF"}])
    with pytest.raises(AllProIdentityError, match="unresolved All-Pro identity collision"):
        F._build_allpro(upcoming, _colliding_allpro(), target_season=2025)


def test_identity_collision_is_not_swallowed_into_zeros_by_the_injury_handler(monkeypatch):
    """The specific regression: the broad `except Exception` must not catch this."""
    upcoming = pd.DataFrame([{
        "home_team": "KC", "away_team": "SF",
        "home_allpro_last_3_years_weighted": 10.0,
        "away_allpro_last_3_years_weighted": 8.0,
        "home_allpro_prev_year": 2.0, "away_allpro_prev_year": 1.0,
    }])

    class _FakeInj:
        def to_pandas(self):
            return pd.DataFrame([{
                "season": 2025, "week": 1, "team": "KC",
                "full_name": "Unresolved Twin", "report_status": "Out"}])

    monkeypatch.setattr(F.nfl, "load_injuries", lambda *a, **k: _FakeInj())
    with pytest.raises(AllProIdentityError):
        F._build_injuries(upcoming, _colliding_allpro(), target_season=2025,
                          target_week=1)


def test_an_unavailable_injury_feed_still_falls_back_to_zeros(monkeypatch):
    """The intended fallback must survive: source-unavailable is NOT an identity failure."""
    upcoming = pd.DataFrame([{
        "home_team": "KC", "away_team": "SF",
        "home_allpro_last_3_years_weighted": 10.0,
        "away_allpro_last_3_years_weighted": 8.0,
        "home_allpro_prev_year": 2.0, "away_allpro_prev_year": 1.0,
    }])

    def _boom(*a, **k):
        raise ConnectionError("nflverse unreachable")

    monkeypatch.setattr(F.nfl, "load_injuries", _boom)
    out = F._build_injuries(upcoming, pd.DataFrame(
        [{"Pos": "LB", "Player": "Someone Else", "Team": "KC", "Year": 2024,
          "Side": "defense"}]), target_season=2025, target_week=1)
    assert float(out["diff_active_allpro_weighted"].iloc[0]) == 0.0
    assert float(out["diff_injured_count"].iloc[0]) == 0.0


def test_the_handler_is_bounded_in_source():
    """A future edit must not re-broaden the handler."""
    src = (_B / "features.py").read_text(encoding="utf-8")
    body = src[src.index("def _build_injuries"):src.index("def _build_coach_win_pct")]
    assert "except AllProIdentityError:" in body, \
        "the identity re-raise was removed from _build_injuries"
    assert body.index("except AllProIdentityError:") < body.index("except Exception as e:"), \
        "the broad handler precedes the identity handler and will swallow it"
