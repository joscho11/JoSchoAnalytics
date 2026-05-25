---
name: never-mention-commits
description: User handles all git commits themselves. Never mention commits, ask "ready to commit?", or summarize work as "commit-ready" state
metadata:
  type: feedback
---

The user handles all git commits themselves. They never want me to mention commits in any form.

**Don't say:**
- "Want me to commit this?"
- "Ready to commit?"
- "You're good to commit"
- "Commit when ready"
- "Final state ready for commit"
- "Suggested commit message"
- Working-tree summaries framed as "what you're committing"

**Why:** They've made this explicit multiple times. They commit themselves on their own schedule. The commit-prompting is annoying noise.

**How to apply:**
- When work is done, end the response with what changed and what's next (or just stop).
- If summarizing changes, describe them as "the changes" or "what's in the working tree", not as a commit preview.
- Don't propose commit messages unless explicitly asked.
- Don't list files as a commit-ready summary at the end of every task.
- Just do the work and let them handle git on their end.
