#!/usr/bin/env python3
"""
process_contribution.py — triggered by GitHub Actions when a corpse: issue is opened.
Parses the code block from the issue, appends to the corpus, updates state and README.
"""
import base64
import json
import os
import re
import sys
from datetime import date, datetime

import urllib.request
import urllib.error


REPO = "LakshmiSravyaVedantham/LakshmiSravyaVedantham"
STATE_FILE = "game/state.json"
CORPUS_FILE = "game/corpus.b64"
README_FILE = "README.md"
ISSUE_URL = f"https://github.com/{REPO}/issues/new?template=corpse-contribution.yml"


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


def extract_code_block(body):
    """Extract Python code from triple-backtick block in issue body."""
    # Match ```python ... ``` or ``` ... ```
    pattern = r"```(?:python)?\s*\n(.*?)```"
    match = re.search(pattern, body, re.DOTALL)
    if match:
        return match.group(1).rstrip("\n")
    return None


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
            hall_lines.append(f"- [Week {entry['week']} reveal]({entry['issue_url']}) — {entry['contributors']} contributor(s)")
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
    with open(README_FILE, "r") as f:
        content = f.read()

    pattern = r"<!-- CORPSE_START -->.*?<!-- CORPSE_END -->"
    if re.search(pattern, content, re.DOTALL):
        new_content = re.sub(pattern, game_section, content, flags=re.DOTALL)
    else:
        # Insert at top
        new_content = game_section + "\n\n---\n\n" + content

    with open(README_FILE, "w") as f:
        f.write(new_content)


def main():
    token = os.environ.get("GITHUB_TOKEN")
    issue_body = os.environ.get("ISSUE_BODY", "")
    issue_number = os.environ.get("ISSUE_NUMBER")
    issue_user = os.environ.get("ISSUE_USER", "anonymous")

    if not issue_number:
        print("ERROR: ISSUE_NUMBER not set", file=sys.stderr)
        sys.exit(1)

    issue_number = int(issue_number)

    # Extract code block
    code = extract_code_block(issue_body)
    if not code:
        comment = "❌ No Python code block found. Please wrap your code in ` ```python ``` ` markers."
        github_api("POST", f"/repos/{REPO}/issues/{issue_number}/comments",
                   {"body": comment}, token)
        sys.exit(1)

    lines = [l for l in code.split("\n") if l.strip()]
    if len(lines) < 3:
        comment = f"❌ Your contribution has only {len(lines)} non-empty line(s). The rules require at least **3 lines**. Feel free to open a new issue with more code!"
        github_api("POST", f"/repos/{REPO}/issues/{issue_number}/comments",
                   {"body": comment}, token)
        sys.exit(1)

    # Load state
    with open(STATE_FILE, "r") as f:
        state = json.load(f)

    # Check for duplicate contributors (optional: allow multiple)
    # Load and decode corpus
    with open(CORPUS_FILE, "r") as f:
        corpus_b64 = f.read().strip()

    if corpus_b64:
        corpus = base64.b64decode(corpus_b64).decode("utf-8")
    else:
        corpus = ""

    # Append new code
    separator = f"\n# --- @{issue_user} ---\n"
    corpus = corpus + separator + code + "\n"

    # Extract new last line
    code_lines = [l for l in code.split("\n") if l.strip()]
    new_last_line = code_lines[-1]

    # Update state
    state["contributor_count"] += 1
    if issue_user not in state["contributors"]:
        state["contributors"].append(issue_user)
    state["last_line"] = new_last_line

    # Re-encode corpus
    corpus_b64_new = base64.b64encode(corpus.encode("utf-8")).decode("ascii")

    # Write files
    with open(CORPUS_FILE, "w") as f:
        f.write(corpus_b64_new)

    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)
        f.write("\n")

    # Regenerate README
    game_section = build_game_section(state)
    update_readme(game_section)

    # GitHub API: add label, post comment, close issue
    # Create label if it doesn't exist (ignore errors)
    try:
        github_api("POST", f"/repos/{REPO}/labels",
                   {"name": "corpse-accepted", "color": "7057ff", "description": "Accepted Exquisite Corpse contribution"}, token)
    except Exception:
        pass  # Label likely already exists

    try:
        github_api("POST", f"/repos/{REPO}/issues/{issue_number}/labels",
                   ["corpse-accepted"], token)
    except Exception:
        pass

    comment_body = (
        f"✅ **Woven in!** Thanks @{issue_user}!\n\n"
        f"The next player will continue from:\n\n"
        f"```python\n{new_last_line}\n```\n\n"
        f"🧩 Contributors this week: **{state['contributor_count']}** · "
        f"📅 Reveal in **{days_until(state['reveal_date'])} day(s)**\n\n"
        f"_[▶ Invite a friend to play]({ISSUE_URL})_"
    )
    github_api("POST", f"/repos/{REPO}/issues/{issue_number}/comments",
               {"body": comment_body}, token)

    github_api("PATCH", f"/repos/{REPO}/issues/{issue_number}",
               {"state": "closed", "state_reason": "completed"}, token)

    print(f"✅ Contribution from @{issue_user} processed. Contributor #{state['contributor_count']}.")
    print(f"   New last line: {new_last_line}")


if __name__ == "__main__":
    main()
