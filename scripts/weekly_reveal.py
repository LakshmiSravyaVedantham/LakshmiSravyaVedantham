#!/usr/bin/env python3
"""
weekly_reveal.py — triggered every Sunday at noon UTC via GitHub Actions schedule.
Reveals the accumulated corpus, saves history, resets game state for next week.
"""
import base64
import json
import os
import sys
from datetime import date, datetime, timedelta

import urllib.request
import urllib.error


REPO = "LakshmiSravyaVedantham/LakshmiSravyaVedantham"
STATE_FILE = "game/state.json"
CORPUS_FILE = "game/corpus.b64"
README_FILE = "README.md"
HISTORY_DIR = "game/history"
ISSUE_URL = f"https://github.com/{REPO}/issues/new?template=corpse-contribution.yml"

SEED_LINES = [
    "    return sorted(data, key=lambda x: x['entropy'], reverse=True)",
    "    raise ValueError(f\"Expected convergence at step {step}, got {delta:.6f}\")",
    "    yield from self._traverse(node.left, depth + 1)",
    "    self.cache[key] = (result, time.time() + self.ttl)",
    "    return np.dot(weights, features) + self.bias",
    "    if not self.visited.add(node): return",
    "    loss = -torch.mean(torch.log(probs + 1e-8))",
    "    return {k: v for k, v in zip(self.keys, row) if v is not None}",
    "    signal = butter_bandpass_filter(raw, 0.5, 40, fs=256)",
    "    assert len(queue) == 0, f\"Unprocessed items: {queue}\"",
]


def github_api(method, path, body=None, token=None):
    url = f"https://api.github.com{path}"
    data = json.dumps(body).encode() if body else None
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "exquisite-corpse-bot",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"GitHub API error {e.code}: {e.read().decode()}", file=sys.stderr)
        raise


def next_sunday():
    today = date.today()
    days_ahead = 6 - today.weekday()  # Sunday = 6
    if days_ahead <= 0:
        days_ahead += 7
    return (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")


def days_until(reveal_date_str):
    reveal = datetime.strptime(reveal_date_str, "%Y-%m-%d").date()
    delta = (reveal - date.today()).days
    return max(0, delta)


def format_reveal_date(reveal_date_str):
    reveal = datetime.strptime(reveal_date_str, "%Y-%m-%d")
    return reveal.strftime("%A %b %-d")


def build_game_section(state):
    last_line = state["last_line"]
    count = state["contributor_count"]
    reveal_date = state["reveal_date"]
    days = days_until(reveal_date)
    reveal_label = format_reveal_date(reveal_date)

    if state.get("hall_of_reveals"):
        hall_lines = []
        for entry in state["hall_of_reveals"]:
            hall_lines.append(
                f"- [Week {entry['week']} reveal]({entry['issue_url']}) — {entry['contributors']} contributor(s)"
            )
        hall_section = "\n".join(hall_lines)
    else:
        hall_section = "_(First reveal coming Sunday!)_"

    return f"""<!-- CORPSE_START -->
## 🧩 Exquisite Corpse

> Collaborative blind-coding. Each player sees only the **last line** written before them.
> The full program is hidden and revealed every Sunday. No one knows what it becomes.

### ✍️ Your Prompt

Continue from this exact line:

```python
{last_line}
```

**[▶ Play now — open an Issue]({ISSUE_URL})**

Rules: write 3+ lines of Python continuing from above. No peeking at `game/corpus.b64`.

### This Round
🧩 Contributors: **{count}** · 📅 Reveal in: **{days} day{"s" if days != 1 else ""}** ({reveal_label})

### Hall of Reveals
{hall_section}
<!-- CORPSE_END -->"""


def update_readme(game_section):
    import re
    with open(README_FILE, "r") as f:
        content = f.read()

    pattern = r"<!-- CORPSE_START -->.*?<!-- CORPSE_END -->"
    if re.search(pattern, content, re.DOTALL):
        new_content = re.sub(pattern, game_section, content, flags=re.DOTALL)
    else:
        new_content = game_section + "\n\n---\n\n" + content

    with open(README_FILE, "w") as f:
        f.write(new_content)


def main():
    token = os.environ.get("GITHUB_TOKEN")

    with open(STATE_FILE, "r") as f:
        state = json.load(f)

    week = state["week"]
    contributors = state["contributors"]
    contributor_count = state["contributor_count"]

    with open(CORPUS_FILE, "r") as f:
        corpus_b64 = f.read().strip()

    if contributor_count == 0:
        print(f"No contributions for week {week}. Resetting with a new seed.")
        new_seed_idx = week % len(SEED_LINES)
        new_seed = SEED_LINES[new_seed_idx]

        # Post a "no contributions" issue
        try:
            github_api(
                "POST", f"/repos/{REPO}/issues",
                {
                    "title": f"🎭 Week {week} — No contributions received",
                    "body": (
                        f"No one contributed to the Exquisite Corpse this week.\n\n"
                        f"The game resets now. Come play next week!\n\n"
                        f"**New prompt:**\n```python\n{new_seed}\n```\n\n"
                        f"[▶ Play now]({ISSUE_URL})"
                    ),
                    "labels": [],
                },
                token,
            )
        except Exception as e:
            print(f"Warning: could not post no-contribution issue: {e}", file=sys.stderr)

    else:
        # Decode corpus
        corpus = base64.b64decode(corpus_b64).decode("utf-8") if corpus_b64 else ""

        # Save history file
        history_path = f"{HISTORY_DIR}/week_{week:03d}.py"
        header_lines = [
            f"# Exquisite Corpse — Week {week}",
            f"# Revealed: {date.today().isoformat()}",
            f"# Contributors ({contributor_count}): {', '.join('@' + c for c in contributors)}",
            "#" + "-" * 60,
            "",
        ]
        history_content = "\n".join(header_lines) + corpus

        with open(history_path, "w") as f:
            f.write(history_content)

        print(f"Saved history to {history_path}")

        # Create reveal issue
        history_url = f"https://github.com/{REPO}/blob/main/{history_path}"
        issue_body = (
            f"# 🎭 Week {week} Reveal — The Accidental Program\n\n"
            f"**{contributor_count} contributor(s):** {', '.join('@' + c for c in contributors)}\n\n"
            f"No single person designed this. Each player saw only the last line.\n\n"
            "```python\n"
            f"{corpus}"
            "```\n\n"
            f"[📁 View saved file]({history_url})\n\n"
            "---\n"
            "_The game resets now. A new prompt will appear in the README. Come play next week!_"
        )

        try:
            result = github_api(
                "POST", f"/repos/{REPO}/issues",
                {
                    "title": f"🎭 Week {week} Reveal — The Accidental Program",
                    "body": issue_body,
                    "labels": [],
                },
                token,
            )
            reveal_issue_url = result.get("html_url", "")
            print(f"Posted reveal issue: {reveal_issue_url}")
        except Exception as e:
            print(f"Warning: could not post reveal issue: {e}", file=sys.stderr)
            reveal_issue_url = ""

        # Update hall of reveals in state
        hall_entry = {
            "week": week,
            "issue_url": reveal_issue_url,
            "contributors": contributor_count,
        }
        if "hall_of_reveals" not in state:
            state["hall_of_reveals"] = []
        state["hall_of_reveals"].append(hall_entry)

        new_seed_idx = week % len(SEED_LINES)
        new_seed = SEED_LINES[new_seed_idx]

    # Reset state for next week
    state["week"] = week + 1
    state["reveal_date"] = next_sunday()
    state["last_line"] = new_seed
    state["contributor_count"] = 0
    state["contributors"] = []

    # Reset corpus to new seed
    new_corpus_b64 = base64.b64encode((new_seed + "\n").encode()).decode("ascii")

    with open(CORPUS_FILE, "w") as f:
        f.write(new_corpus_b64)

    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)
        f.write("\n")

    # Regenerate README
    game_section = build_game_section(state)
    update_readme(game_section)

    print(f"✅ Week {week} revealed. Game reset to week {week + 1}.")
    print(f"   New seed: {new_seed}")
    print(f"   Next reveal: {state['reveal_date']}")


if __name__ == "__main__":
    main()
