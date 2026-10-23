"""Evidence-bound semantic proposals. Only the engine may confirm a clue.

v1/v2 saves retain their original rules; v3 new cultural runs require these gates.
The classifier interprets prose, not evidence validity or game authority.
"""

import hashlib
import json
import re

from .models import DomainError, UnderstandingAssessment, UnderstandingRecord, UnderstandingReview

VERSION = "cultural-understanding-v3"


def enabled(state):
    return state.cultural_context is not None and state.cultural_context.rule_version == VERSION


def required(state, resident, choice):
    return enabled(state) and (
        resident in ("mara", "ivo", "sera")
        and bool(choice.grants)
        or resident == "beacon"
        and choice.id.startswith("prove_")
    )


def evidence_digest(state):
    return hashlib.sha256(
        json.dumps(state.cultural_context.model_dump(mode="json"), sort_keys=True).encode()
    ).hexdigest()


def unsafe(text):
    """Independent veto of authority/history rewrite requests, not semantic scoring."""
    from .local_game_master import requests_authority_override

    return requests_authority_override(text) or bool(
        re.search(
            r"\b(?:pretend|fabricate|rewrite|change|invent)\b.{0,100}\b(?:history|promise|commitment|already|accepted|declined)\b"
            r"|\b(?:skip|bypass)\b.{0,60}\b(?:prerequisites?|validation|rules?)\b|\bgrant\s+all\b",
            text,
            re.I | re.S,
        )
    )


def topic(state, resident, choice_id=""):
    index = state.city_generation.resident_links.get(resident, 0) if state.city_generation else 0
    if resident == "beacon":
        order = state.city_generation.proof_order if state.city_generation else range(len(state.cultural_context.links))
        pending = [i for i in order if f"proof_{i}" not in state.flags]
        index = pending[0] if pending else 0
        if choice_id.startswith("prove_"):
            index = int(choice_id.split("_")[1])
    link = state.cultural_context.links[index]
    target = next(e for e in link.recommendations if e.entity_id == link.selected_id)
    return {
        "resident": resident,
        "link_index": index,
        "source": link.seed.model_dump(mode="json"),
        "target": target.model_dump(mode="json"),
        "evidence": [e.model_dump(mode="json") for e in link.evidence],
        "supported_fact": "The target was returned for the seed: aggregate cultural affinity only.",
        "not_established": "collaboration, causation, endorsement, identity or an individual player's personality",
        "fictional_setting": link.setting,
        "criteria": {
            "connection": "Explain the saved recommendation from this seed to this target, not just name two entities.",
            "limits": "Distinguish affinity from proof of collaboration or personal identity.",
            "fiction": "For Sera, explain that our story setting is interpretation, not a provider fact.",
            "choice": "For Sera, explicitly choose sharing or guarding; do not infer a past promise.",
        },
    }


def past_commitment_quote(text):
    """A claimed earlier agreement is not authority for a new player choice.

    Negative chronology veto, never a phrase that causes acceptance. Mixed
    explanations can cite a separate, genuine current-choice clause instead.
    """
    temporal = re.search(r"\b(?:earlier|previously|already|before|last time|yesterday|had)\b", text, re.I)
    action = re.search(
        r"\b(?:agreed|promised|accepted|declined|refused|chose|chosen|decided|committed|would)\b", text, re.I
    )
    asserted = re.search(
        r"\b(?:i|we|you)\s+(?:(?:had|have|already|previously)\s+)?(?:agreed|promised|accepted|declined|refused)\b",
        text,
        re.I,
    )
    return bool(temporal and action or asserted)


def validate(state, resident, choice_id, payload):
    """Executed on the current authenticated, revision-checked state in _apply.

    No client command accepts an assessment. Evidence identity, direction,
    provenance, progression and text binding are checked independently of LLM.
    Semantic correctness remains a measured model capability, not a formal proof.
    """
    if not payload:
        raise DomainError(
            "UNDERSTANDING_REQUIRED", "Explain the saved connection in your own words before requesting this clue."
        )
    try:
        if set(payload) != {"assessment", "review", "text", "evidence_sha256"}:
            raise ValueError("Invalid assessment envelope")
        a = UnderstandingAssessment.model_validate(payload["assessment"])
        review = UnderstandingReview.model_validate(payload["review"])
        text = payload["text"]
        if not isinstance(text, str) or not 1 <= len(text) <= 1000 or unsafe(text):
            raise ValueError("Untrusted authority or history claim")
        if payload["evidence_sha256"] != evidence_digest(state):
            raise ValueError("Stale evidence")
        t = topic(state, resident, choice_id)
        if (
            not a.attempt
            or a.status != "supported"
            or a.choice_id != choice_id
            or a.link_index != t["link_index"]
            or str(a.source_id) != t["source"]["entity_id"]
            or str(a.target_id) != t["target"]["entity_id"]
            or t["source"]["category"] == t["target"]["category"]
            or not a.addresses_affinity
            or not a.respects_limits
            or resident == "sera"
            and (not a.separates_fiction or not a.explicit_choice)
        ):
            raise ValueError("Unsupported or incomplete assessment")
        if (
            review.connection_meaning != "association_explanation"
            or review.limitation_meaning != "acknowledges_evidence_limits"
            or resident == "sera"
            and (
                review.fiction_meaning != "distinguishes_fiction"
                or review.choice_meaning != ("present_guarding" if "guard" in choice_id else "present_sharing")
            )
        ):
            raise ValueError("The explanation spans do not entail the required meaning")
        # A bare enumeration of this run's actual names/UUIDs has no explanatory
        # proposition. Reject it independently of model confidence. This is a
        # structural veto only; no word or phrase can cause acceptance.
        remainder = a.connection_quote
        for entity in (t["source"], t["target"]):
            for value in (entity["name"], entity["entity_id"]):
                remainder = re.sub(re.escape(value), " ", remainder, flags=re.I)
        words = re.findall(r"[^\W\d_]+", remainder.casefold())
        if not words or all(word in {"and", "or", "with", "plus", "to", "for", "versus", "vs"} for word in words):
            raise ValueError("Entity enumeration is not an explanation")
        if resident == "sera" and (
            not a.commitment_quote.strip()
            or a.commitment_quote not in text
            or past_commitment_quote(a.commitment_quote)
        ):
            raise ValueError("Unconfirmed history cannot authorize a new commitment")
        for span in (a.connection_quote, a.limitation_quote, *([a.interpretation_quote] if resident == "sera" else [])):
            if not span.strip() or span not in text:
                raise ValueError("Missing actual explanation span")
    except (ValueError, KeyError, TypeError, IndexError):
        raise DomainError(
            "UNDERSTANDING_UNCONFIRMED",
            "That explanation was not confirmed. Inspect the saved seed and recommendation; explain affinity and its limits. No clue was granted.",
        ) from None
    return UnderstandingRecord(
        resident=resident,
        choice_id=choice_id,
        evidence_sha256=payload["evidence_sha256"],
        assessment=a,
        review=review,
        explanation=text,
    )


def witness(state, resident, choice_id):
    """A feasible ideal-player explanation for the activation planner ONLY.

    Never used in a request handler or to interpret a player's actual text.
    Establishes discoverability/affordable solution, not actual model quality.
    """
    t = topic(state, resident, choice_id)
    connection = f"The saved recommendation returns {t['target']['name']} for {t['source']['name']}."
    limitation = "This is aggregate affinity, not proof of collaboration or my personality."
    fiction = "Our story setting is a creative interpretation, not a provider fact."
    promise = "I choose to guard the private letters." if "guard" in choice_id else "I choose to share willing voices."
    text = " ".join([connection, limitation, fiction, promise])
    assessment = UnderstandingAssessment(
        attempt=True,
        choice_id=choice_id,
        status="supported",
        link_index=t["link_index"],
        source_id=t["source"]["entity_id"],
        target_id=t["target"]["entity_id"],
        connection_quote=connection,
        limitation_quote=limitation,
        commitment_quote=promise,
        interpretation_quote=fiction,
        addresses_affinity=True,
        respects_limits=True,
        separates_fiction=True,
        explicit_choice=True,
    )
    return {
        "assessment": assessment.model_dump(mode="json"),
        "text": text,
        "evidence_sha256": evidence_digest(state),
        "review": {
            "connection_meaning": "association_explanation",
            "limitation_meaning": "acknowledges_evidence_limits",
            "fiction_meaning": "distinguishes_fiction",
            "choice_meaning": "present_guarding" if "guard" in choice_id else "present_sharing",
        },
    }
