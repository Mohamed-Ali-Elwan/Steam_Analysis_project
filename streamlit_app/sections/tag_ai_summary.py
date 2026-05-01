import hashlib
import json
import os
import random
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd
import streamlit as st
from pymongo import MongoClient

from data_processing import get_mongodb_config, resolve_database_name

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openrouter/free"
DEFAULT_MAX_REVIEWS = 80
DEFAULT_SAMPLE_STRATEGY = "balanced"
PROMPT_VERSION = "tag-review-summary-v1"
SUMMARY_COLLECTION_ENV = "MONGODB_TAG_SUMMARIES_COLLECTION"
DEFAULT_SUMMARY_COLLECTION = "tag_review_ai_summaries"
REVIEW_TEXT_FIELDS = ("review_text", "text", "review", "content")
REVIEW_SENTIMENT_FIELD = "recommendation"
REVIEW_ID_FIELD = "recommendationid"


def get_openrouter_config():
    secrets = {}
    try:
        secrets = st.secrets.get("openrouter", {})
    except Exception:
        secrets = {}

    return {
        "api_key": os.getenv("OPENROUTER_API_KEY") or secrets.get("api_key", ""),
        "model": os.getenv("OPENROUTER_MODEL")
        or secrets.get("model", DEFAULT_MODEL),
    }


def get_summary_collection_name():
    secrets = {}
    try:
        secrets = st.secrets.get("mongodb", {})
    except Exception:
        secrets = {}
    return (
        os.getenv(SUMMARY_COLLECTION_ENV)
        or secrets.get("tag_summaries_collection")
        or DEFAULT_SUMMARY_COLLECTION
    )


def get_summary_collection():
    config = get_mongodb_config()
    if not config["uri"]:
        raise ValueError("MongoDB URI is missing.")

    client = MongoClient(config["uri"], serverSelectionTimeoutMS=10000)
    client.admin.command("ping")
    database_name = resolve_database_name(client, config["database"])
    if database_name is None:
        client.close()
        raise ValueError("No MongoDB database was found for saving tag summaries.")

    collection = client[database_name][get_summary_collection_name()]
    collection.create_index("tag")
    collection.create_index("created_at")
    return client, collection


def build_tag_review_contexts(games_df, reviews_df, dlcs_df=None):
    if (
        games_df is None
        or games_df.empty
        or reviews_df is None
        or reviews_df.empty
        or "app_id" not in games_df.columns
        or "tag" not in games_df.columns
    ):
        return {}

    games = {}
    for game in games_df.to_dict("records"):
        game_id = _normalize_id(game.get("app_id"))
        if not game_id:
            continue
        tags = _extract_tags(game.get("tag"))
        if not tags:
            continue
        games[game_id] = {
            "id": game_id,
            "name": game.get("name") or game.get("title") or f"App {game_id}",
            "tags": tags,
        }

    dlc_index = _build_dlc_index(dlcs_df)
    contexts = {}
    review_counter = 0

    for review in reviews_df.to_dict("records"):
        game_id = _resolve_review_game_id(review, games)
        game = games.get(game_id)
        if not game:
            continue

        text = _extract_review_text(review)
        if not text:
            continue

        review_counter += 1
        review_obj = {
            "ref": f"R#{review_counter}",
            "id": str(review.get(REVIEW_ID_FIELD, review_counter)),
            "text": text,
            "sentiment": str(review.get(REVIEW_SENTIMENT_FIELD, "Unknown")),
            "game_name": game["name"],
            "game_id": game_id,
        }

        for tag in game["tags"]:
            context = contexts.setdefault(
                tag,
                {
                    "reviews": [],
                    "game_ids": set(),
                    "game_names": set(),
                    "dlcs_by_id": {},
                },
            )
            context["reviews"].append(review_obj)
            context["game_ids"].add(game_id)
            context["game_names"].add(game["name"])
            for dlc in dlc_index.get(game_id, []):
                dlc_id = _normalize_id(dlc.get("app_id")) or str(len(context["dlcs_by_id"]))
                context["dlcs_by_id"][dlc_id] = dlc

    for context in contexts.values():
        context["game_ids"] = sorted(context["game_ids"])
        context["game_names"] = sorted(context["game_names"], key=str.casefold)
        context["dlcs"] = list(context.pop("dlcs_by_id").values())

    return contexts


def get_saved_summary(tag, model, max_reviews=DEFAULT_MAX_REVIEWS):
    key = build_summary_key(tag, model, max_reviews)
    client = None
    try:
        client, collection = get_summary_collection()
        return collection.find_one({"_id": key}, {"_id": 0})
    finally:
        if client is not None:
            client.close()


def save_summary(summary):
    client = None
    try:
        client, collection = get_summary_collection()
        collection.replace_one({"_id": summary["_id"]}, summary, upsert=True)
    finally:
        if client is not None:
            client.close()


def build_summary_key(tag, model, max_reviews=DEFAULT_MAX_REVIEWS):
    payload = {
        "tag": tag,
        "model": model,
        "max_reviews": max_reviews,
        "prompt_version": PROMPT_VERSION,
    }
    encoded = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def generate_and_save_summary(
    tag,
    tag_context,
    api_key,
    model=DEFAULT_MODEL,
    max_reviews=DEFAULT_MAX_REVIEWS,
):
    sampled_reviews = sample_reviews(tag_context["reviews"], max_reviews=max_reviews)
    prompt = build_prompt(
        tag=tag,
        reviews=sampled_reviews,
        dlcs=tag_context.get("dlcs", []),
        game_names=tag_context.get("game_names", []),
        total_reviews=len(tag_context["reviews"]),
    )
    response = call_openrouter(prompt, api_key=api_key, model=model)
    positive_count = sum(1 for review in tag_context["reviews"] if _is_positive(review))
    positive_pct = (
        round(positive_count / len(tag_context["reviews"]) * 100, 1)
        if tag_context["reviews"]
        else 0
    )
    now = datetime.now(timezone.utc)
    summary = {
        "_id": build_summary_key(tag, model, max_reviews),
        "tag": tag,
        "model_requested": model,
        "model_used": response.get("model", model),
        "prompt_version": PROMPT_VERSION,
        "sample_strategy": DEFAULT_SAMPLE_STRATEGY,
        "max_reviews": max_reviews,
        "total_reviews": len(tag_context["reviews"]),
        "sampled_reviews": len(sampled_reviews),
        "positive_pct": positive_pct,
        "game_count": len(tag_context.get("game_ids", [])),
        "dlc_count": len(tag_context.get("dlcs", [])),
        "game_names": tag_context.get("game_names", [])[:30],
        "review_ids": [review["id"] for review in sampled_reviews],
        "analysis": response["analysis"],
        "usage": response.get("usage", {}),
        "created_at": now,
        "updated_at": now,
    }
    save_summary(summary)
    return summary


def sample_reviews(reviews, max_reviews=DEFAULT_MAX_REVIEWS):
    if len(reviews) <= max_reviews:
        return list(reviews)

    random.seed(42)
    positives = [review for review in reviews if _is_positive(review)]
    negatives = [review for review in reviews if not _is_positive(review)]
    half = max_reviews // 2
    selected_positive = random.sample(positives, min(half, len(positives)))
    selected_negative = random.sample(negatives, min(half, len(negatives)))
    selected = selected_positive + selected_negative

    remaining = max_reviews - len(selected)
    if remaining > 0:
        selected_ids = {id(review) for review in selected}
        pool = [review for review in reviews if id(review) not in selected_ids]
        selected.extend(random.sample(pool, min(remaining, len(pool))))

    random.shuffle(selected)
    return selected


def build_prompt(tag, reviews, dlcs, game_names, total_reviews):
    reviews_block = "\n\n".join(_format_review(review) for review in reviews)
    dlcs_block = _format_dlcs(dlcs)
    games = ", ".join(game_names[:10]) + ("..." if len(game_names) > 10 else "")
    positive_count = sum(1 for review in reviews if _is_positive(review))

    return f"""
Analyze Steam player reviews for the game tag: {tag}

Games represented: {games or "Unknown"}
Sample size: {len(reviews)} reviews from {total_reviews} total tag reviews.
Sentiment in sample: {positive_count} positive, {len(reviews) - positive_count} negative.

Citation rules:
- Every concrete claim must include a short direct quote from a review.
- Cite reviews as [R#N, Game: Name].
- Do not invent player feedback that is not supported by the reviews.

Return this exact report structure:

## 1. Must-Focus Features
List 5 to 8 features developers should prioritize. For each item include:
- Insight
- 2 short review quotes with citations
- Concrete developer action

## 2. Common Complaints To Avoid
List the top 5 pain points. For each item include:
- Problem
- 2 short review quotes with citations
- Concrete fix

## 3. DLC & Content Ideas
List 5 DLC or content ideas. For each idea include:
- Working title
- Review evidence with citations
- Scope: Small Patch, Medium Expansion, or Full DLC
- Existing DLC cross-reference if useful

## 4. Evidence Summary
- Overall sentiment: Mostly Positive, Mixed, or Mostly Negative
- Top 3 praised aspects, each with one quote
- Top 3 criticized aspects, each with one quote
- Most referenced game in the sample

Close with a 60-word Executive Summary for a studio head.
Do not mention your role or identity.

Existing DLCs:
{dlcs_block}

Player reviews:
{reviews_block}
""".strip()


def call_openrouter(prompt, api_key, model=DEFAULT_MODEL):
    if not api_key:
        raise ValueError("OpenRouter API key is missing.")

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You summarize Steam reviews for product and game-development "
                    "decisions. Use only evidence from the supplied reviews."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.35,
        "max_tokens": 3000,
    }
    data = json.dumps(payload).encode("utf-8")
    request = Request(
        OPENROUTER_URL,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8501",
            "X-Title": "Steam Games Analytics Dashboard",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=120) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenRouter request failed ({exc.code}): {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"OpenRouter request failed: {exc.reason}") from exc

    try:
        content = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"OpenRouter returned an unexpected response: {result}") from exc

    return {
        "analysis": content,
        "model": result.get("model", model),
        "usage": result.get("usage", {}),
    }


def _normalize_id(value):
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text


def _extract_tags(value):
    if value is None:
        return []
    if isinstance(value, float) and pd.isna(value):
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(tag).strip() for tag in value if str(tag).strip()]
    text = str(value).strip()
    return [text] if text else []


def _build_dlc_index(dlcs_df):
    if dlcs_df is None or dlcs_df.empty:
        return {}

    index = {}
    for dlc in dlcs_df.to_dict("records"):
        parent_id = _normalize_id(dlc.get("parent_app_id")) or _normalize_id(
            dlc.get("game_id")
        )
        if not parent_id:
            continue
        index.setdefault(parent_id, []).append(dlc)
    return index


def _resolve_review_game_id(review, games):
    direct_id = _normalize_id(review.get("app_id"))
    if direct_id in games:
        return direct_id
    return _normalize_id(review.get("parent_app_id"))


def _extract_review_text(review):
    for field in REVIEW_TEXT_FIELDS:
        value = review.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _is_positive(review):
    sentiment = str(review.get("sentiment", "")).strip().lower()
    if not sentiment:
        return False
    return "not" not in sentiment and sentiment not in {"0", "false", "negative"}


def _format_review(review):
    text = review["text"].replace("\n", " ").strip()
    if len(text) > 900:
        text = text[:897].rstrip() + "..."
    return (
        f"[{review['ref']} | {review['sentiment']} | "
        f"Game: {review['game_name']} | ReviewID: {review['id']}]\n"
        f"\"{text}\""
    )


def _format_dlcs(dlcs):
    if not dlcs:
        return "No DLC data available."

    lines = []
    for dlc in dlcs[:15]:
        title = dlc.get("title") or dlc.get("name") or "Unnamed DLC"
        description = dlc.get("description") or dlc.get("short_description") or ""
        description = str(description).replace("\n", " ").strip()
        if len(description) > 160:
            description = description[:157].rstrip() + "..."
        lines.append(f"- {title}" + (f": {description}" if description else ""))
    return "\n".join(lines)
