#!/usr/bin/env python3
"""
process_trait.py — Process a Build-a-Bot trait contribution from a GitHub Issue.

Triggered by: .github/workflows/process-trait.yml
When: An issue is opened with title starting with "trait:"

Reads ISSUE_BODY, ISSUE_NUMBER, ISSUE_USER from environment variables.
"""

import json
import os
import re
import sys
import urllib.parse
import urllib.request
import urllib.error
from datetime import date, timedelta


REPO = os.environ.get("GITHUB_REPOSITORY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
ISSUE_BODY = os.environ.get("ISSUE_BODY", "")
ISSUE_NUMBER = os.environ.get("ISSUE_NUMBER", "")
ISSUE_USER = os.environ.get("ISSUE_USER", "")

STATE_PATH = "game/state.json"
README_PATH = "README.md"


def github_api(method: str, path: str, data: dict | None = None) -> dict:
    """Make an authenticated GitHub API request."""
    url = f"https://api.github.com/repos/{REPO}{path}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
        "User-Agent": "build-a-bot-action",
    }
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        print(f"GitHub API error {e.code} on {method} {path}: {error_body}")
        return {}


def ensure_label(name: str, color: str, description: str = "") -> None:
    """Create the label if it doesn't exist yet."""
    existing = github_api("GET", f"/labels/{urllib.parse.quote(name)}")
    if not existing.get("id"):
        github_api("POST", "/labels", {
            "name": name,
            "color": color,
            "description": description,
        })


def parse_trait(body: str) -> str | None:
    """
    Extract trait from the '### Your trait' section of the issue body.
    Returns the stripped trait string, or None if not found/invalid.
    """
    # GitHub issue forms render the textarea content after the section header
    match = re.search(
        r"###\s*Your trait\s*\n+(.*?)(?:\n###|\Z)",
        body,
        re.DOTALL | re.IGNORECASE,
    )
    if not match:
        return None
    trait = match.group(1).strip()
    # Remove any accidental code block markers
    trait = re.sub(r"^```[^\n]*\n?", "", trait)
    trait = re.sub(r"\n?```$", "", trait)
    return trait.strip() or None


def next_sunday() -> date:
    today = date.today()
    days_ahead = 6 - today.weekday()  # weekday(): Monday=0, Sunday=6
    if days_ahead <= 0:
        days_ahead += 7
    return today + timedelta(days=days_ahead)


def days_until(target: str) -> int:
    target_date = date.fromisoformat(target)
    return max(0, (target_date - date.today()).days)


def format_reveal_date(reveal_date: str) -> str:
    d = date.fromisoformat(reveal_date)
    return d.strftime("%A %b %-d")


def build_game_section(state: dict) -> str:
    """Regenerate the README section between <!-- BOT_START --> and <!-- BOT_END -->."""
    bot_name = state["bot_name"]
    traits = state["traits"]
    contributor_count = state["contributor_count"]
    reveal_date = state["reveal_date"]
    hall_of_bots = state.get("hall_of_bots", [])

    days_left = days_until(reveal_date)
    reveal_display = format_reveal_date(reveal_date)

    if traits:
        traits_md = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(traits))
    else:
        traits_md = "_(none yet — be the first to shape this week's bot!)_"

    issue_url = (
        f"https://github.com/{REPO}/issues/new?template=bot-trait.yml"
        if REPO
        else "https://github.com/issues/new?template=bot-trait.yml"
    )

    if hall_of_bots:
        hall_lines = "\n".join(
            f"- [{entry['bot_name']} reveal]({entry['issue_url']}) — "
            f"{entry['contributors']} contributor(s)"
            for entry in hall_of_bots
        )
    else:
        hall_lines = "_(First bot reveal coming Sunday!)_"

    section = f"""## 🤖 Build-a-Bot

> Each week, we collectively build an AI personality — one trait at a time.
> Every Sunday, the bot's full character is revealed. Anyone can contribute.

### This Week's Bot: {bot_name}

**Traits so far:**
{traits_md}

**[▶ Add a trait — open an Issue]({issue_url})**

> Examples: *"Speaks like a Victorian novelist"* · *"Obsessed with bread"* ·
> *"Ends every reply with an unexpected plot twist"* · *"Refuses to use the letter E"*

### This Round
🎭 Traits: **{contributor_count}** · 📅 Reveal in: **{days_left} days** ({reveal_display})

### Hall of Bots
{hall_lines}"""

    return section


def update_readme(state: dict) -> None:
    """Replace content between <!-- BOT_START --> and <!-- BOT_END --> in README."""
    with open(README_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    new_section = build_game_section(state)
    new_content = re.sub(
        r"<!-- BOT_START -->.*?<!-- BOT_END -->",
        f"<!-- BOT_START -->\n{new_section}\n<!-- BOT_END -->",
        content,
        flags=re.DOTALL,
    )
    with open(README_PATH, "w", encoding="utf-8") as f:
        f.write(new_content)


def main() -> None:
    # --- Parse and validate trait ---
    trait = parse_trait(ISSUE_BODY)

    if not trait:
        github_api("POST", f"/issues/{ISSUE_NUMBER}/comments", {
            "body": (
                "❌ Could not find a trait in your submission. "
                "Please make sure to fill in the **Your trait** field in the issue form."
            )
        })
        sys.exit(0)

    if len(trait) < 5:
        github_api("POST", f"/issues/{ISSUE_NUMBER}/comments", {
            "body": (
                f"❌ Your trait is too short ({len(trait)} chars). "
                "Please describe the trait in at least 5 characters."
            )
        })
        sys.exit(0)

    if len(trait) > 150:
        github_api("POST", f"/issues/{ISSUE_NUMBER}/comments", {
            "body": (
                f"❌ Your trait is too long ({len(trait)} chars). "
                "Please keep it under 150 characters."
            )
        })
        sys.exit(0)

    # --- Load state ---
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        state = json.load(f)

    # --- Duplicate check (case-insensitive) ---
    existing_lower = [t.lower() for t in state["traits"]]
    if trait.lower() in existing_lower:
        github_api("POST", f"/issues/{ISSUE_NUMBER}/comments", {
            "body": (
                "❌ That trait (or a very similar one) has already been added this week. "
                "Try something more unique!"
            )
        })
        sys.exit(0)

    # --- Append trait ---
    state["traits"].append(trait)
    state["contributor_count"] += 1
    if ISSUE_USER not in state["contributors"]:
        state["contributors"].append(ISSUE_USER)

    # --- Save state ---
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
        f.write("\n")

    # --- Update README ---
    update_readme(state)

    # --- Build trait list for comment ---
    trait_list = "\n".join(f"  {i + 1}. {t}" for i, t in enumerate(state["traits"]))
    bot_name = state["bot_name"]
    n = state["contributor_count"]

    # --- Post success comment ---
    github_api("POST", f"/issues/{ISSUE_NUMBER}/comments", {
        "body": (
            f"✅ Trait added! **{bot_name}** now has **{n}** trait(s).\n\n"
            f"**Current traits:**\n{trait_list}\n\n"
            f"The full bot personality will be revealed this Sunday! 🤖"
        )
    })

    # --- Ensure label exists and apply it ---
    ensure_label("trait-accepted", "7c3aed", "Build-a-Bot trait accepted")
    github_api("POST", f"/issues/{ISSUE_NUMBER}/labels", {"labels": ["trait-accepted"]})

    # --- Close issue ---
    github_api("PATCH", f"/issues/{ISSUE_NUMBER}", {
        "state": "closed",
        "state_reason": "completed",
    })

    print(f"✅ Trait accepted: '{trait}' from @{ISSUE_USER}. {bot_name} now has {n} trait(s).")


if __name__ == "__main__":
    main()
