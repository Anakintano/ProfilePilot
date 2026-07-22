"""Deterministic, template-based Scribe generator -- zero network calls, the
default experience with no API keys configured (this local-first app's
common case), and the guaranteed final fallback when all real providers
fail. Mirrors the philosophy of
services/worker/app/providers/fake_provider.py: genuinely readable output
built from the user's actual input, not a static placeholder regardless of
what was typed.
"""
from __future__ import annotations

import time

import jsonschema

from ..contracts import load_schema

_POST_SCHEMA = load_schema("scribe_post_output.schema.json")
_COMMENT_SCHEMA = load_schema("scribe_comment_output.schema.json")

_POST_HASHTAG_BASE = ["careergrowth", "linkedin", "professionaldevelopment"]


def _clean(text: str | None) -> str:
    return " ".join((text or "").split())


def _excerpt(text: str, max_len: int = 80) -> str:
    if len(text) <= max_len:
        return text
    cut = text[:max_len]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(",;:.- ") + "..."


def _hashtag_from_words(words: list[str]) -> str:
    cleaned = [w for w in words if w.isalnum()]
    if not cleaned:
        return ""
    return "".join(w.capitalize() for w in cleaned)


# --- Post templates, one per ScribeStyle ------------------------------------

def _post_professional(topic: str, sketch: str) -> str:
    body = sketch or (
        f"Over the past few months I've been thinking more deliberately about {topic}, "
        "and it's changed how I approach my day-to-day work."
    )
    return (
        f"A quick reflection on {topic}.\n\n"
        f"{body}\n\n"
        f"If you're navigating something similar with {topic}, I'd welcome hearing how you're approaching it."
    )


def _post_storytelling(topic: str, sketch: str) -> str:
    hook = sketch or f"A few months ago, I hit a wall with {topic}."
    return (
        f"{hook}\n\n"
        "I didn't have a playbook for it, so I leaned on trial, error, and a lot of questions to "
        f"the people around me. Slowly, {topic} stopped feeling like an obstacle and started feeling "
        "like a skill I was actually building.\n\n"
        f"The lesson that stuck with me: progress on {topic} rarely looks like a straight line -- "
        "and that's fine."
    )


def _post_thought_leadership(topic: str, sketch: str) -> str:
    stance = sketch or f"most advice about {topic} focuses on the wrong thing"
    return (
        f"Unpopular opinion: {stance}.\n\n"
        f"Here's why: {topic} is usually treated as a checklist, when it's actually a judgment call "
        "that depends on context most generic advice ignores.\n\n"
        f"The people who get {topic} right aren't following a template -- they're asking better "
        "questions before they act."
    )


def _post_casual(topic: str, sketch: str) -> str:
    body = sketch or f"been thinking about {topic} a lot lately and wanted to share a quick take"
    return (
        f"ok real talk -- {body}\n\n"
        f"nothing groundbreaking here, just sharing in case it's useful to someone else figuring out "
        f"{topic} right now.\n\n"
        "curious what's worked for you -- drop it in the comments!"
    )


def _post_data_driven(topic: str, sketch: str) -> str:
    lead = sketch or f"Most conversations about {topic} skip the numbers."
    return (
        f"{lead}\n\n"
        f"A few things worth sitting with when it comes to {topic}:\n"
        f"- Teams that track {topic} explicitly report clearer decision-making\n"
        "- The biggest gains usually come from small, consistent changes -- not one big overhaul\n"
        f"- What gets measured around {topic} is what actually gets improved\n\n"
        f"If you're not currently measuring anything related to {topic}, that's the first place to start."
    )


def _post_listicle(topic: str, sketch: str) -> str:
    intro = sketch or f"A few things I've learned about {topic}:"
    return (
        f"{intro}\n\n"
        f"1. Start smaller than feels comfortable with {topic} -- momentum matters more than scope.\n"
        f"2. Ask for feedback on {topic} earlier than you think you need to.\n"
        f"3. Document what you learn about {topic} as you go, not after the fact.\n"
        f"4. Progress on {topic} compounds -- the first weeks are the slowest.\n\n"
        "What would you add to this list?"
    )


_POST_TEMPLATES = {
    "professional": _post_professional,
    "storytelling": _post_storytelling,
    "thought_leadership": _post_thought_leadership,
    "casual": _post_casual,
    "data_driven": _post_data_driven,
    "listicle": _post_listicle,
}


def generate_post(style: str, topic: str, rough_sketch: str | None) -> tuple[dict, dict]:
    start = time.monotonic()
    topic_clean = _clean(topic) or "my career journey"
    sketch = _clean(rough_sketch)
    template = _POST_TEMPLATES.get(style, _post_professional)
    post_text = template(topic_clean, sketch)

    topic_tag = _hashtag_from_words(topic_clean.split()[:2])
    candidates = ([topic_tag] if topic_tag else []) + _POST_HASHTAG_BASE
    seen: set[str] = set()
    hashtags: list[str] = []
    for tag in candidates:
        low = tag.lower()
        if low in seen:
            continue
        seen.add(low)
        hashtags.append(tag)

    result = {"post_text": post_text, "hashtags": hashtags[:5]}
    jsonschema.validate(result, _POST_SCHEMA)

    latency_ms = int((time.monotonic() - start) * 1000)
    meta = {"model": "template-v1", "prompt_tokens": 0, "completion_tokens": 0, "latency_ms": latency_ms}
    return result, meta


# --- Comment templates, one per ScribeCommentType ----------------------------

def _comment_engaging(excerpt: str) -> str:
    return (
        f'This resonates -- "{excerpt}" is a great point. What\'s been the biggest shift in how '
        "you approach this since you started?"
    )


def _comment_supportive(excerpt: str) -> str:
    return (
        f'Really well said. "{excerpt}" is the kind of perspective more people need to hear -- '
        "thanks for sharing it."
    )


def _comment_insightful(excerpt: str) -> str:
    return (
        f'Good breakdown. One thing I\'d add to "{excerpt}" -- context often matters as much as '
        "the approach itself, especially early on."
    )


def _comment_question(excerpt: str) -> str:
    return (
        f'Curious to dig into this more -- when you say "{excerpt}", what changed first: the '
        "mindset or the process?"
    )


def _comment_congratulatory(excerpt: str) -> str:
    return f'Congratulations -- "{excerpt}" is a genuine milestone. Well deserved, and excited to see what\'s next.'


_COMMENT_TEMPLATES = {
    "engaging": _comment_engaging,
    "supportive": _comment_supportive,
    "insightful": _comment_insightful,
    "question": _comment_question,
    "congratulatory": _comment_congratulatory,
}


def generate_comment(post_content: str, comment_type: str) -> tuple[dict, dict]:
    start = time.monotonic()
    content_clean = _clean(post_content) or "this post"
    template = _COMMENT_TEMPLATES.get(comment_type, _comment_engaging)
    comment_text = template(_excerpt(content_clean))

    result = {"comment_text": comment_text}
    jsonschema.validate(result, _COMMENT_SCHEMA)

    latency_ms = int((time.monotonic() - start) * 1000)
    meta = {"model": "template-v1", "prompt_tokens": 0, "completion_tokens": 0, "latency_ms": latency_ms}
    return result, meta
