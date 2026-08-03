"""Registry of TikTok videos surfaced in the Film Room tab.

To add a video after posting it:
  1. Append an entry to VIDEOS below (slug, title, subtitle, tiktok_url, video_id, breakdown_file).
  2. Drop its in-depth breakdown as markdown in  video_breakdowns/<breakdown_file>.
The `video_id` is the number at the end of the TikTok URL (.../video/<id>).
"""

# The channel intro — featured at the top of the tab as "what this is about".
INTRO_VIDEO = {
    "title": "Welcome to JoScho Analytics",
    "tiktok_url": "https://www.tiktok.com/@joschoanalytics/video/7660252294327307550",
    "video_id": "7660252294327307550",
    "blurb": (
        "Model-backed sports analysis, not hot takes — built by an ML engineer, with the code "
        "public on GitHub. Watch a short, then open the deep dive the video couldn't fit."
    ),
    "about": (
        "### 📺 About the Film Room\n\n"
        "Every call here comes from a machine-learning model I built and run live — the code's "
        "public on my GitHub, and I show you the reasoning, not just the pick. Each short gives "
        "you the headline; the write-up next to it digs into the data the video couldn't fit — "
        "the numbers, the model's reasoning, and the honest case for and against.\n\n"
        "New player and matchup breakdowns land here as I post them."
    ),
}

# Player / topic videos — each gets an embed + a click-to-open written breakdown.
# `archived: True` + `archive_note` adds a compact "📼 Archived — why?" pop-out to the
# card (the note + Draft Board cross-link live inside it; see film_room.render_film_room).
VIDEOS = [
    {
        "slug": "brian-thomas-jr",
        "title": "The Market Is Wrong About Brian Thomas Jr.",
        "date": "2026-07-07",
        "tiktok_url": "https://www.tiktok.com/@joschoanalytics/video/7660252626046553374",
        "video_id": "7660252626046553374",
        "breakdown_file": "brian_thomas_jr.md",
        "archived": True,
        "archive_note": (
            "📼 Archived — posted July 7, 2026, before my validation work "
            "finished. This video makes a call about one player using a model "
            "I've since retired. When testing finished, what held up were "
            "group-level patterns and calibrated ranges — never claims about "
            "individual players — and this video doesn't reflect how I work now. "
            "It stays up, "
            "unedited, as part of the record. For what I publish today: the "
            "Draft Board tab."
        ),
    },
    {
        "slug": "makai-lemon",
        "title": "Makai Lemon — Rookie Receiver Profile",
        "subtitle": "2026 · WR, Philadelphia Eagles",
        "date": "2026-07-30",
        "tiktok_url": "https://www.tiktok.com/@joschoanalytics/video/7668110810039717151",
        "video_id": "7668110810039717151",
        "breakdown_file": "makai_lemon.md",
    },
    {
        "slug": "bijan-robinson-jahmyr-gibbs",
        "title": "Bijan Robinson vs. Jahmyr Gibbs",
        "subtitle": "2025 season review · RB, Atlanta / Detroit",
        "date": "2026-08-02",
        "tiktok_url": "https://www.tiktok.com/@joschoanalytics/video/7669558168984309022",
        "video_id": "7669558168984309022",
        "breakdown_file": "bijan_robinson_jahmyr_gibbs.md",
    },
]
