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
VIDEOS = [
    {
        "slug": "brian-thomas-jr",
        "title": "The Market Is Wrong About Brian Thomas Jr.",
        "subtitle": "WR · Jacksonville — Sleeper ADP WR31, our model WR17",
        "date": "2026-07-07",
        "tiktok_url": "https://www.tiktok.com/@joschoanalytics/video/7660252626046553374",
        "video_id": "7660252626046553374",
        "breakdown_file": "brian_thomas_jr.md",
        "teaser": (
            "The short covers the headline. The full breakdown digs into the quarterback "
            "split, the touchdown regression, the honest drops question, and exactly why "
            "the model has him at WR17."
        ),
    },
]
