#!/usr/bin/env python3
"""
weekly_reveal.py — Weekly Build-a-Bot reveal script.

Triggered every Sunday at noon UTC (or manually via workflow_dispatch).

- Loads game/state.json
- If no traits: posts a "no traits" issue, resets state, done
- If traits exist:
  - Generates bot profile (Claude API if ANTHROPIC_API_KEY set, else template)
  - Saves to game/history/week_NNN.md
  - Posts reveal GitHub Issue
  - Appends to hall_of_bots, resets for next week
  - Regenerates README
"""

import json
import os
import re
import sys
import urllib.request
import urllib.error
from datetime import date, timedelta
from pathlib import Path


REPO = os.environ.get("GITHUB_REPOSITORY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

STATE_PATH = "game/state.json"
README_PATH = "README.md"
HISTORY_DIR = Path("game/history")


# ---------------------------------------------------------------------------
# GitHub API helper
# ---------------------------------------------------------------------------

def github_api(method: str, path: str, data: dict | None = None) -> dict:
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
        print(f"GitHub API error {e.code} on {method} {path}: {e.read().decode()}")
        return {}


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def next_sunday() -> date:
    today = date.today()
    days_ahead = 6 - today.weekday()  # Monday=0, Sunday=6
    if days_ahead <= 0:
        days_ahead += 7
    return today + timedelta(days=days_ahead)


def days_until(target: str) -> int:
    return max(0, (date.fromisoformat(target) - date.today()).days)


def format_reveal_date(reveal_date: str) -> str:
    d = date.fromisoformat(reveal_date)
    return d.strftime("%A %b %-d")


# ---------------------------------------------------------------------------
# Reveal content generation
# ---------------------------------------------------------------------------

def _extract_keywords(traits: list[str]) -> list[str]:
    """Pull descriptive words from traits for the template summary."""
    words = []
    skip = {"a", "an", "the", "is", "are", "was", "were", "be",
            "been", "being", "and", "or", "but", "in", "on",
            "at", "to", "for", "of", "with", "by", "from"}
    for trait in traits:
        for word in trait.split():
            clean = re.sub(r"[^a-zA-Z'-]", "", word).lower()
            if clean and clean not in skip and len(clean) > 3:
                words.append(clean)
                break  # one keyword per trait
    return words


def generate_template_reveal(bot_name: str, traits: list[str]) -> str:
    """Build a fun template-based personality card (no API key needed)."""
    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(traits))
    keywords = _extract_keywords(traits)

    if len(traits) == 0:
        summary_combined = "mysterious and undefined"
    elif len(traits) == 1:
        summary_combined = traits[0].lower()
    else:
        summary_combined = ", ".join(keywords) if keywords else "complex and multifaceted"

    first_trait = traits[0] if traits else "something unexpected"
    second_trait = traits[1] if len(traits) > 1 else "surprise you in every interaction"

    return f"""# 🤖 {bot_name} — The Collective Personality

**Traits contributed by the community:**
{numbered}

**Personality Summary:**
{bot_name} would be described as: {summary_combined}.
Approach them expecting: {first_trait}. Don't be surprised if they: {second_trait}.

*Want real AI-powered bot responses? The repo owner can add `ANTHROPIC_API_KEY`
as a GitHub Actions secret to unlock live Claude responses every Sunday.*"""


def generate_claude_reveal(bot_name: str, traits: list[str]) -> str:
    """Call Claude API to generate a bot personality profile with Q&A."""
    numbered_traits = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(traits))
    system_prompt = (
        f"You are {bot_name}, an AI personality built collectively by an online community. "
        f"Your personality is defined entirely by these traits:\n{numbered_traits}\n\n"
        "Stay fully in character. Be creative, consistent, and entertaining."
    )
    user_prompt = (
        f"You are {bot_name}. Answer these 5 questions in character, "
        "based on the personality traits above.\n\n"
        "1. How would you introduce yourself?\n"
        "2. What is your philosophy on life?\n"
        "3. What are you most passionate about?\n"
        "4. What is your biggest quirk?\n"
        "5. Give someone a piece of advice."
    )

    payload = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 1024,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
        "User-Agent": "build-a-bot-action",
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=data,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read().decode())
            qa_text = result["content"][0]["text"]
    except Exception as e:
        print(f"Claude API call failed: {e}. Falling back to template.")
        return generate_template_reveal(bot_name, traits)

    numbered = "\n".join(f"{i + 1}. {t}" for i, t in enumerate(traits))
    return f"""# 🤖 {bot_name} — The Collective Personality

**Traits contributed by the community:**
{numbered}

**{bot_name} speaks:**

{qa_text}

*Powered by Claude (claude-haiku-4-5-20251001) + community creativity.*"""


# ---------------------------------------------------------------------------
# README helpers
# ---------------------------------------------------------------------------

def build_game_section(state: dict) -> str:
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

    return f"""## 🤖 Build-a-Bot

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


def update_readme(state: dict) -> None:
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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # Load state
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        state = json.load(f)

    week = state["week"]
    bot_name = state["bot_name"]
    traits = state["traits"]
    contributor_count = state["contributor_count"]
    contributors = state.get("contributors", [])

    # --- No contributions this week ---
    if contributor_count == 0:
        print(f"No traits this week for {bot_name}. Posting notice and resetting.")
        next_sun = next_sunday()
        next_week = week + 1
        next_bot = f"BOT-{next_week:03d}"

        github_api("POST", "/issues", {
            "title": f"🤖 {bot_name} — No Traits This Week",
            "body": (
                f"No one contributed a trait for **{bot_name}** this week. 😢\n\n"
                f"Next week's bot is **{next_bot}** — be the first to shape its personality!\n\n"
                f"📅 Next reveal: **{next_sun.strftime('%A, %B %-d')}**\n\n"
                f"[▶ Add the first trait](https://github.com/{REPO}/issues/new?template=bot-trait.yml)"
            ),
            "labels": [],
        })

        # Reset state
        state["week"] = next_week
        state["bot_name"] = next_bot
        state["reveal_date"] = next_sun.isoformat()
        state["traits"] = []
        state["contributor_count"] = 0
        state["contributors"] = []

        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
            f.write("\n")

        update_readme(state)
        print("Reset complete.")
        return

    # --- Generate reveal content ---
    print(f"Generating reveal for {bot_name} with {contributor_count} trait(s)...")
    if ANTHROPIC_API_KEY:
        print("ANTHROPIC_API_KEY found — using Claude API.")
        reveal_content = generate_claude_reveal(bot_name, traits)
    else:
        print("No ANTHROPIC_API_KEY — using template reveal.")
        reveal_content = generate_template_reveal(bot_name, traits)

    # Build reveal header with metadata
    contributor_list = ", ".join(f"@{c}" for c in contributors)
    today_str = date.today().strftime("%Y-%m-%d")
    full_reveal = (
        f"<!-- Build-a-Bot Reveal — Week {week} — {today_str} -->\n"
        f"<!-- Contributors ({contributor_count}): {contributor_list} -->\n\n"
        f"{reveal_content}"
    )

    # Save to history
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    history_path = HISTORY_DIR / f"week_{week:03d}.md"
    with open(history_path, "w", encoding="utf-8") as f:
        f.write(full_reveal)
    print(f"Saved reveal to {history_path}")

    # Determine issue title from first trait keywords
    first_trait_words = traits[0].split()[:4] if traits else ["the", "bot", "is", "revealed"]
    title_snippet = " ".join(first_trait_words)
    issue_title = f"🤖 {bot_name} Reveal — \"{title_snippet}...\""

    # Post reveal issue
    issue_body = (
        f"## 🤖 {bot_name} — Weekly Bot Reveal\n\n"
        f"**Week {week}** · Contributors: {contributor_list}\n\n"
        f"---\n\n"
        f"{reveal_content}\n\n"
        f"---\n\n"
        f"*Thanks to everyone who contributed a trait this week!*\n"
        f"*Next week's bot: **BOT-{week + 1:03d}** — "
        f"[add the first trait](https://github.com/{REPO}/issues/new?template=bot-trait.yml)*"
    )
    reveal_issue = github_api("POST", "/issues", {
        "title": issue_title,
        "body": issue_body,
        "labels": [],
    })
    reveal_url = reveal_issue.get("html_url", "")
    print(f"Posted reveal issue: {reveal_url}")

    # --- Update hall_of_bots and reset state ---
    next_week = week + 1
    next_sun = next_sunday()
    next_bot = f"BOT-{next_week:03d}"

    state["hall_of_bots"].append({
        "week": week,
        "bot_name": bot_name,
        "issue_url": reveal_url,
        "contributors": contributor_count,
    })
    state["week"] = next_week
    state["bot_name"] = next_bot
    state["reveal_date"] = next_sun.isoformat()
    state["traits"] = []
    state["contributor_count"] = 0
    state["contributors"] = []

    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
        f.write("\n")

    update_readme(state)
    print(f"State reset to {next_bot}, reveal date {next_sun.isoformat()}.")


if __name__ == "__main__":
    main()
