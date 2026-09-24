"""Film Room: one player, title list, a single TikTok embed.

Hermetic: APP_OFFLINE=1. Renders page_film_room directly, same pattern as
test_site_nav.page harnesses.
"""
import os
import sys
from pathlib import Path

os.environ["APP_OFFLINE"] = "1"

from streamlit.testing.v1 import AppTest

_HERE = Path(__file__).resolve().parents[1]
_SITE_PAGES = _HERE / "site_pages"
sys.path.insert(0, str(_HERE))

from film_room import _embed_src, _sectioned_episodes  # noqa: E402
from video_content import (  # noqa: E402
    DEFAULT_VIDEO_SLUG,
    INTRO_VIDEO,
    LATEST_LEAGUE_HISTORY_VIDEO_SLUG,
    VIDEO_SECTIONS,
    VIDEOS,
)


def _render(tmp_path):
    harness = tmp_path / "h_film_room.py"
    harness.write_text(
        f"import sys; sys.path[:0] = [r'{_HERE}', r'{_SITE_PAGES}']\n"
        "import page_film_room as page\npage.render()\n",
        encoding="utf-8",
    )
    at = AppTest.from_file(str(harness), default_timeout=180).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    return at


def _newest():
    return sorted(VIDEOS, key=lambda v: v.get("date") or "", reverse=True)[0]


def _default():
    return next(v for v in VIDEOS if v["slug"] == DEFAULT_VIDEO_SLUG)


def _md(at):
    return " ".join(str(m.value) for m in at.markdown)


def test_embed_uses_dark_player_not_white_card():
    src = _embed_src("7674314953565670687")
    assert src == "https://www.tiktok.com/player/v1/7674314953565670687"
    assert "embed/v2" not in src


def test_catalog_size_and_expected_slugs():
    assert len(VIDEOS) == 33
    slugs = {item["slug"] for item in VIDEOS}
    assert "brian-thomas-jr" not in slugs
    assert "site-walkthrough" in slugs
    assert "league-history" not in slugs
    assert "ladd-mcconkey" in slugs
    assert "wandale-robinson" in slugs
    assert "jonathan-taylor" in slugs
    assert "jacory-croskey-merritt" in slugs
    assert "derrick-henry" in slugs
    assert "harrison-vs-wilson" in slugs
    assert "davante-adams" in slugs
    assert "chase-brown" in slugs
    assert "kenneth-walker" in slugs
    assert "jadarian-price" in slugs
    assert "garrett-wilson" in slugs
    assert "lamar-jackson" in slugs
    assert DEFAULT_VIDEO_SLUG == "league-history-guide"
    assert DEFAULT_VIDEO_SLUG in slugs
    latest = next(item for item in VIDEOS if item["slug"] == "latest-video-2026-09-24")
    assert latest["video_id"] == "7689224721262562591"
    assert latest["date"] == "2026-09-24"


def test_default_is_league_history_guide(tmp_path):
    at = _render(tmp_path)
    default = _default()
    newest = _newest()
    md = _md(at)
    assert default["title"] in md
    assert newest["slug"] == "latest-video-2026-09-24"
    assert newest["title"] not in md
    assert "Welcome to JoScho Analytics" not in md
    assert "A walk through the JoScho Analytics site" not in md
    watch = [link for link in at.get("link_button") if link.label == "Watch on TikTok"]
    assert len(watch) == 1, "only the selected video should render a Watch link"
    assert watch[0].url == default["tiktok_url"]
    assert default["video_id"] == "7676271983297940766"


def _section_control(at):
    return next(w for w in at.segmented_control if w.key == "film_room_section")


def _episode_box(at):
    return next(w for w in at.selectbox if w.label == "Episode")


def test_picker_lists_every_episode_and_no_retired_intro(tmp_path):
    at = _render(tmp_path)
    labels = [str(b.label) for b in at.button]
    assert not any("Start here" in lbl for lbl in labels)
    assert INTRO_VIDEO is None
    seen = set()
    for key, _label in VIDEO_SECTIONS:
        at = _section_control(at).set_value(key).run()
        assert not at.exception, at.exception
        seen.update(_episode_box(at).options)
    for item in VIDEOS:
        assert item["title"] in seen
    breakdowns = [b for b in at.button if "Full breakdown" in str(b.label)
                  or "What is this?" in str(b.label)]
    assert len(breakdowns) == 1
    captions = {str(c.value) for c in at.caption}
    assert _section_control(at).options == [
        "Walkthroughs",
        "In-season",
        "Draft",
        "Players",
    ]
    assert "Archive" not in captions
    assert not any(label in captions for _key, label in VIDEO_SECTIONS)


def test_catalog_sections():
    newest_first = sorted(
        VIDEOS, key=lambda item: item.get("date") or "", reverse=True
    )
    grouped = {
        label: [item["slug"] for item in items]
        for label, items in _sectioned_episodes(newest_first)
    }
    assert grouped["Site walkthroughs"] == [
        "site-walkthrough",
        LATEST_LEAGUE_HISTORY_VIDEO_SLUG,
    ]
    assert "Predictions & weekly" not in grouped, "empty sections are hidden"
    assert grouped["In-season analysis"] == [
        "latest-video-2026-09-24",
        "wr-te-advanced-stats",
        "rb-advanced-stats-part-2",
        "rb-advanced-stats-part-1",
        "week-1-signal",
        "chargers-week-1-loss",
        "latest-video-2026-09-11",
    ]
    assert grouped["Draft strategy & research"] == [
        "rb-wr-draft-strategy",
        "qb-te-draft-timing",
        "draft-order",
        "how-to-leverage-adp-wr",
        "how-to-leverage-adp-rb",
        "how-to-leverage-adp-te",
        "how-to-leverage-adp-qb",
        "how-to-leverage-adp-guide",
    ]
    assert grouped["Player breakdowns"] == [
        "lamar-jackson",
        "garrett-wilson",
        "jadarian-price",
        "chase-brown",
        "kenneth-walker",
        "davante-adams",
        "harrison-vs-wilson",
        "derrick-henry",
        "jacory-croskey-merritt",
        "jonathan-taylor",
        "wandale-robinson",
        "ladd-mcconkey",
        "jameson-williams",
        "jefferson-deep-dive",
        "bijan-robinson-jahmyr-gibbs",
        "makai-lemon",
    ]
    assert "Archive" not in grouped
    assert newest_first[0]["slug"] == "latest-video-2026-09-24"


def test_every_episode_has_a_known_content_section():
    active_sections = {key for key, _label in VIDEO_SECTIONS}
    for item in VIDEOS:
        assert item["section"] in active_sections, item["slug"]
        assert not item.get("archived"), item["slug"]


def test_switching_episode_swaps_the_embed(tmp_path):
    at = _render(tmp_path)
    default = _default()
    other = next(v for v in VIDEOS if v["slug"] != default["slug"])
    if other["section"] != default["section"]:
        at = _section_control(at).set_value(other["section"]).run()
        assert not at.exception, at.exception
    at = _episode_box(at).set_value(other["slug"]).run()
    assert not at.exception, at.exception
    assert not at.error, [e.value for e in at.error]
    watch = [link for link in at.get("link_button") if link.label == "Watch on TikTok"]
    assert len(watch) == 1
    assert watch[0].url == other["tiktok_url"]
    assert watch[0].url != default["tiktok_url"]


def test_shared_video_url_selects_episode(tmp_path):
    other = next(v for v in VIDEOS if v["slug"] != DEFAULT_VIDEO_SLUG)
    harness = tmp_path / "film_query.py"
    harness.write_text(
        f"import sys; sys.path[:0] = [r'{_HERE}', r'{_HERE / 'site_pages'}']\n"
        "import streamlit as st\n"
        f"st.query_params['video'] = {other['slug']!r}\n"
        "import page_film_room as p\n"
        "p.render()\n",
        encoding="utf-8",
    )
    at = AppTest.from_file(str(harness), default_timeout=180).run()
    assert not at.exception, at.exception
    watch = [link for link in at.get("link_button") if link.label == "Watch on TikTok"]
    assert len(watch) == 1 and watch[0].url == other["tiktok_url"]


def test_breakdown_files_exist_when_provided():
    for item in VIDEOS:
        if item.get("breakdown_file"):
            path = _HERE / "video_breakdowns" / item["breakdown_file"]
            assert path.is_file(), item["slug"]
        assert item["video_id"]
        assert item["video_id"] in item["tiktok_url"]


def test_site_walkthrough_is_the_posted_tiktok():
    item = next(v for v in VIDEOS if v["slug"] == "site-walkthrough")
    assert item["video_id"] == "7676601401342037279"
    assert item["date"] == "2026-08-21"
    assert item["section"] == "site-walkthroughs"
    assert item["tiktok_url"] == (
        "https://www.tiktok.com/@joschoanalytics/video/7676601401342037279"
    )


def test_latest_league_history_guide_constant_still_points_at_the_walkthrough():
    item = next(v for v in VIDEOS if v["slug"] == LATEST_LEAGUE_HISTORY_VIDEO_SLUG)
    assert item["video_id"] == "7676271983297940766"
    assert item["date"] == "2026-08-20"
    assert item["section"] == "site-walkthroughs"


def test_newest_episode_is_latest_video():
    newest = _newest()
    assert newest["slug"] == "latest-video-2026-09-24"
    assert newest["video_id"] == "7689224721262562591"
    assert newest["date"] == "2026-09-24"


def test_breakdowns_and_registry_do_not_disclose_sleeper_mix():
    phrases = ("25% sleeper", "75/25", "75% independent")
    blob = " ".join(
        (_HERE / "video_breakdowns" / item["breakdown_file"]).read_text(encoding="utf-8")
        for item in VIDEOS if item.get("breakdown_file")
    )
    blob += " ".join(str(item.get("archive_note") or "") for item in VIDEOS)
    lower = blob.lower()
    for phrase in phrases:
        assert phrase not in lower, f"Sleeper mix leaked into Film Room copy: {phrase}"


_LIVE_SYNC_PROBE = '''
import os, sys
os.environ["APP_OFFLINE"] = "1"
tmp, here, marker = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path[:0] = [tmp, here, os.path.join(here, "site_pages")]
from pathlib import Path
from streamlit.testing.v1 import AppTest

harness = Path(tmp) / "h_probe.py"
harness.write_text("import page_film_room as page" + chr(10) + "page.render()" + chr(10), encoding="utf-8")


def seen_titles():
    at = AppTest.from_file(str(harness), default_timeout=180).run()
    assert not at.exception, at.exception
    seg = next(w for w in at.segmented_control if w.key == "film_room_section")
    titles = set()
    for key in list(seg.options):
        at = seg.set_value(key).run()
        assert not at.exception, at.exception
        titles.update(next(w for w in at.selectbox if w.label == "Episode").options)
        seg = next(w for w in at.segmented_control if w.key == "film_room_section")
    return titles


before = seen_titles()
vc = Path(tmp) / "video_content.py"
text = vc.read_text(encoding="utf-8")
entry = (
    "    {" + chr(10)
    + '        "slug": "live-sync-probe",' + chr(10)
    + '        "title": "' + marker + '",' + chr(10)
    + '        "subtitle": "probe",' + chr(10)
    + '        "date": "2099-01-01",' + chr(10)
    + '        "section": "player-breakdowns",' + chr(10)
    + '        "tiktok_url": "https://www.tiktok.com/@joschoanalytics/video/1",' + chr(10)
    + '        "video_id": "1",' + chr(10)
    + '        "breakdown_file": "makai_lemon.md",' + chr(10)
    + "    }," + chr(10)
)
vc.write_text(text.replace("VIDEOS = [" + chr(10), "VIDEOS = [" + chr(10) + entry, 1), encoding="utf-8")
os.utime(vc, None)
after = seen_titles()
print("BEFORE_HAS_MARKER", marker in before)
print("AFTER_HAS_MARKER", marker in after)
'''


def test_registry_edit_reaches_a_live_process(tmp_path):
    """A registry-only push must show up in an already-running Cloud process.

    Cloud copies the new video_content.py into a live interpreter. film_room
    copies its names at import time and its own file did not change, so before
    this was fixed the page kept serving the old list until a manual reboot.
    """
    import shutil
    import subprocess

    shutil.copy(_HERE / "film_room.py", tmp_path / "film_room.py")
    shutil.copy(_HERE / "video_content.py", tmp_path / "video_content.py")
    probe = tmp_path / "probe.py"
    probe.write_text(_LIVE_SYNC_PROBE, encoding="utf-8")
    marker = "Live Sync Probe Episode"
    run = subprocess.run(
        [sys.executable, str(probe), str(tmp_path), str(_HERE), marker],
        capture_output=True, text=True, timeout=300,
    )
    assert run.returncode == 0, run.stderr[-2000:]
    assert "BEFORE_HAS_MARKER False" in run.stdout
    assert "AFTER_HAS_MARKER True" in run.stdout, run.stdout + run.stderr[-1000:]
