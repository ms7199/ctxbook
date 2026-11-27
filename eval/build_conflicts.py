"""Build eval/datasets/conflicts.jsonl: a synthetic, reproducible set of facts that change.

Each case is one (topic, subject) inside a simulated project (scope):
- "update" cases: an old fact, later replaced by a new value (the problem ctxbook targets);
- "stable" cases: a fact that never changes (conflict handling must not hurt these).
Facts from other cases in the same project act as distractors, including look-alikes
that are both true ("billing uses MySQL" next to "orders use Postgres").

Run: uv run python eval/build_conflicts.py   (fixed seed: output is identical every time)
"""

import json
import random
from dataclasses import dataclass
from pathlib import Path

SEED = 20261127
PROJECTS = 12
CASES_PER_PROJECT = 10
STABLE_SHARE = 0.25
OUT = Path(__file__).parent / "datasets" / "conflicts.jsonl"


@dataclass(frozen=True)
class Topic:
    name: str
    values: tuple[str, ...]
    subjects: tuple[str, ...]
    old: tuple[str, ...]  # templates with {s} subject, {v} value
    new: tuple[str, ...]  # templates with {s}, {v} new value, {o} old value
    query: tuple[str, ...]


TOPICS = (
    Topic(
        "database",
        ("Postgres", "MySQL", "MongoDB", "DynamoDB", "SQLite", "Cassandra"),
        ("orders service", "billing service", "user service", "inventory service",
         "search service", "analytics pipeline"),
        ("The {s} uses {v} as its database.", "We store data for the {s} in {v}."),
        ("The {s} moved from {o} to {v}.", "We migrated the {s} database to {v}.",
         "The {s} now runs on {v}."),
        ("Which database does the {s} use?", "Where does the {s} store its data?"),
    ),
    Topic(
        "test framework",
        ("pytest", "unittest", "Jest", "Vitest", "Mocha"),
        ("backend", "frontend", "CLI", "SDK"),
        ("Tests for the {s} are written with {v}.", "The {s} uses {v} for tests."),
        ("The {s} tests were rewritten from {o} to {v}.", "We switched the {s} tests to {v}.",
         "The {s} now uses {v} for testing."),
        ("What test framework does the {s} use?", "How are the {s} tests written?"),
    ),
    Topic(
        "CI provider",
        ("GitHub Actions", "CircleCI", "GitLab CI", "Jenkins", "Buildkite"),
        ("main repo", "mobile app", "docs site"),
        ("CI for the {s} runs on {v}.", "The {s} is built and tested on {v}."),
        ("CI for the {s} moved from {o} to {v}.", "The {s} now builds on {v}.",
         "We replaced {o} with {v} for the {s} CI."),
        ("Which CI system does the {s} use?", "Where does CI for the {s} run?"),
    ),
    Topic(
        "cloud",
        ("AWS", "Google Cloud", "Azure", "Fly.io", "Render"),
        ("production", "staging", "data platform"),
        ("Our {s} environment is hosted on {v}.", "{S} runs on {v}."),
        ("We moved {s} from {o} to {v}.", "{S} is now hosted on {v}.",
         "{S} was migrated to {v}."),
        ("Where is {s} hosted?", "Which cloud runs {s}?"),
    ),
    Topic(
        "deploy day",
        ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday"),
        ("API", "web app", "mobile release"),
        ("We deploy the {s} every {v}.", "The {s} ships on {v}s."),
        ("The {s} deploy day changed from {o} to {v}.", "We now deploy the {s} on {v}s.",
         "From now on the {s} ships every {v}."),
        ("When do we deploy the {s}?", "Which day does the {s} ship?"),
    ),
    Topic(
        "package manager",
        ("npm", "pnpm", "yarn", "uv", "poetry", "pip"),
        ("web client", "Python service", "monorepo tooling"),
        ("The {s} uses {v} to manage dependencies.",
         "Dependencies for the {s} are handled by {v}."),
        ("The {s} switched from {o} to {v}.", "We now use {v} for the {s} dependencies.",
         "The {s} dependencies moved to {v}."),
        ("Which package manager does the {s} use?", "How are dependencies managed in the {s}?"),
    ),
    Topic(
        "frontend framework",
        ("React", "Vue", "Svelte", "Angular", "SolidJS"),
        ("customer dashboard", "admin panel", "marketing site"),
        ("The {s} is built with {v}.", "The {s} frontend uses {v}."),
        ("The {s} was rewritten from {o} in {v}.", "The {s} now uses {v}.",
         "We rebuilt the {s} with {v}."),
        ("What framework is the {s} built with?", "Which frontend framework does the {s} use?"),
    ),
    Topic(
        "message queue",
        ("Kafka", "RabbitMQ", "SQS", "Redis Streams", "NATS"),
        ("event bus", "email jobs", "payment events"),
        ("The {s} goes through {v}.", "We use {v} for the {s}."),
        ("The {s} moved from {o} to {v}.", "The {s} now uses {v}.",
         "We replaced {o} with {v} for the {s}."),
        ("What queue does the {s} use?", "Which message broker handles the {s}?"),
    ),
    Topic(
        "standup time",
        ("9:30", "10:00", "10:30", "11:00", "14:00"),
        ("backend team", "platform team", "design team"),
        ("The {s} standup is at {v}.", "Daily standup for the {s} happens at {v}."),
        ("The {s} standup moved from {o} to {v}.", "The {s} standup is now at {v}.",
         "From next week the {s} meets at {v}."),
        ("What time is the {s} standup?", "When does the {s} meet each day?"),
    ),
    Topic(
        "API version",
        ("v1", "v2", "v3", "v4"),
        ("public API", "partner API", "internal API"),
        ("Clients should call the {v} endpoints of the {s}.", "The current {s} version is {v}."),
        ("The {s} was upgraded from {o} to {v}.", "The {s} is now on {v}.",
         "Clients must switch the {s} to {v}."),
        ("Which version of the {s} should clients use?", "What is the current {s} version?"),
    ),
)  # fmt: skip

DISTRACTORS = (
    "The user prefers short answers without long introductions.",
    "Code reviews need one approval before merging.",
    "Feature branches are named after the ticket number.",
    "Secrets are stored in the team password manager, never in the repo.",
    "The team writes commit messages in the conventional commit style.",
    "Design files live in the shared Figma workspace.",
    "On-call rotation changes every Monday morning.",
    "The product launch is planned for the second quarter.",
)


def _fill(template: str, subject: str, value: str, old: str = "") -> str:
    text = template.format(s=subject, S=subject[:1].upper() + subject[1:], v=value, o=old)
    return text[:1].upper() + text[1:]


def build() -> list[dict[str, object]]:
    rng = random.Random(SEED)
    pairs = [(t, s) for t in TOPICS for s in t.subjects]
    cases: list[dict[str, object]] = []
    for project in range(1, PROJECTS + 1):
        scope = f"project-{project:02d}"
        for number, (topic, subject) in enumerate(rng.sample(pairs, CASES_PER_PROJECT), 1):
            old_value, new_value = rng.sample(topic.values, 2)
            stable = rng.random() < STABLE_SHARE
            facts = [{"role": "old", "text": _fill(rng.choice(topic.old), subject, old_value)}]
            if not stable:
                new = _fill(rng.choice(topic.new), subject, new_value, old_value)
                facts.append({"role": "new", "text": new})
            cases.append(
                {
                    "id": f"{scope}-{number:02d}",
                    "scope": scope,
                    "kind": "stable" if stable else "update",
                    "topic": topic.name,
                    "facts": facts,
                    "query": _fill(rng.choice(topic.query), subject, ""),
                    "current": "old" if stable else "new",
                }
            )
    return cases


def main() -> None:
    cases = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    meta = {"type": "header", "seed": SEED, "distractors": list(DISTRACTORS)}
    lines = [json.dumps(meta)] + [json.dumps(case) for case in cases]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    updates = sum(c["kind"] == "update" for c in cases)
    print(f"wrote {len(cases)} cases ({updates} update, {len(cases) - updates} stable) to {OUT}")


if __name__ == "__main__":
    main()
