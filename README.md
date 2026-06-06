# instar-skill-expert

Expert knowledge skill for [Project Instar](https://github.com/thegman54/project-instar). Provides a structured knowledge base with on-demand retrieval — procedures, runbooks, decision trees, and domain-specific instructions.

## What It Does

Stores expert entries (topic + category + full markdown content) and exposes three tools the bot calls at runtime:

- **expert_list** — browse topics by category
- **expert_read** — load full instructions for a specific topic
- **expert_search** — fuzzy match when the bot isn't sure which topic applies

A compact index (topic → one-liner summary) is baked into CLAUDE.md at profile startup. The bot sees what's available and pulls full instructions on demand, keeping base context small while making hundreds of procedures accessible.

## Install

Zip and upload via the Instar admin UI, or copy into `tool-executor/src/tools/expert/`.

```bash
zip -r instar-skill-expert.zip . -x '.git/*' 'README.md'
# Upload via POST /skills/upload or the admin Skills page
```

## Usage

1. Set a profile's **Expert** field to `skill:expert`
2. Open the **Knowledge** admin panel on the profile card
3. Add entries with category, topic, summary, content, tags, and cross-references
4. Launch the profile — the CLAUDE.md includes the expert index

## Entry Structure

| Field | Description |
|-------|-------------|
| topic | Unique identifier (e.g., `rollback_procedure`) |
| category | Grouping (e.g., `deployments`, `monitoring`) |
| summary | One-liner for the CLAUDE.md index |
| content | Full markdown instructions — procedures, steps, decision trees |
| priority | `critical`, `high`, `normal`, `low` |
| tags | Keywords for search |
| refs | Cross-references to other topic names |

## Bot Behavior

When the bot matches a user request to an expert topic:
1. Tells the user what topic it found
2. Asks for confirmation
3. Loads full instructions via `expert_read`
4. Follows the instructions precisely

Max 3 chained `expert_read` calls per turn (for cross-references).

## License

MIT
