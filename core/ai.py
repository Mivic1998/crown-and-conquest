"""Gemini integration and deterministic AI fallback logic.

This module isolates all direct interaction with Google's Gemini API from the
rest of Crown & Conquest.

It supports three AI-assisted workflows:

- evaluating attacker and defender rallying cries;
- evaluating a ruler's response to a kingdom crisis;
- generating concise premium policy advice.

Gemini is used as a qualitative evaluator and adviser rather than as an
authoritative gameplay engine. Raw model output is parsed and validated by
Django before it is returned to the calling view or simulation service.

Important numerical gameplay decisions remain under application control:

- rallying-cry scores are clamped;
- rally modifiers are recalculated by Django;
- event scores are recalculated by backend code;
- event consequences are applied by deterministic rules;
- battle outcomes are calculated by the warfare simulation;
- policy advice does not directly change kingdom state.

Every public evaluation function includes conservative fallback behaviour so
that missing configuration, malformed output, or external API failure does not
prevent the wider application from continuing to operate.
"""

import json

from django.conf import settings
from google import genai
from google.genai import types
from kingdoms.simulation import preview_policy_effects


def get_gemini_client():
    """Create and return a configured Gemini client when an API key exists.

    Returns:
        A ``genai.Client`` configured with ``settings.GEMINI_API_KEY``, or
        ``None`` when no key has been configured.

    Called by:
        - ``evaluate_rallying_cry()``;
        - ``evaluate_event_response()``;
        - ``evaluate_policy_decision()``.
    """
    # The API key originates from Django settings, which reads it from an
    # environment variable. It is never passed into a template or browser.
    if not getattr(settings, "GEMINI_API_KEY", None):
        return None

    return genai.Client(api_key=settings.GEMINI_API_KEY)


def safe_json_loads(text):#try to convert JSON text into Python data so it can be used throughout the app; if it fails, return None instead of crashing.
    """Parse Gemini response text as JSON without propagating common errors.

    Args:
        text: The raw ``response.text`` returned by Gemini.

    Returns:
        The decoded Python object when parsing succeeds, otherwise ``None``.

    Only direct JSON is accepted. The Gemini calls request the
    ``application/json`` response MIME type and a response schema, so this
    helper does not attempt to remove Markdown fences or extract JSON from
    surrounding prose.
    """
    try:
        return json.loads(text) #Takes JSON formatted text and converts it into python data 
    except (TypeError, json.JSONDecodeError):
        # Returning None allows each calling workflow to enter its own
        # feature-specific fallback path.
        return None


def clamp(value, minimum, maximum):
    """Restrict a numeric value to an inclusive minimum and maximum.

    Args:
        value: Numeric value to constrain.
        minimum: Lowest permitted result.
        maximum: Highest permitted result.

    Returns:
        ``value`` when it lies within the range, otherwise the nearest bound.

    This helper prevents AI-provided scores or derived gameplay modifiers from
    exceeding the limits defined by the application.
    """
    return max(minimum, min(maximum, value))


def evaluate_rallying_cry(rallying_cry):
    """Evaluate a battle speech and return bounded warfare assessment data.

    Gemini is asked to judge leadership, inspiration, and practicality using a
    deliberately strict scoring standard. Although the prompt requests a rally
    modifier, the application discards that proposed numerical value and
    derives its own modifier from the validated category average.

    Args:
        rallying_cry: Validated speech text supplied by ``WarForm``.

    Returns:
        A dictionary containing:

        - ``leadership_score``;
        - ``inspiration_score``;
        - ``practicality_score``;
        - ``rally_modifier``;
        - ``feedback``.

    The attacker workflow stores these values when a War is created. The
    defender workflow stores them when a response is submitted, and the
    warfare simulation currently evaluates the defender speech again during
    resolution.

    On any failure, conservative 4/10 scores and a 0.98 modifier are returned.
    """
    # The prompt frames Gemini as a strict evaluator to reduce score inflation.
    # It includes only the submitted rallying cry and evaluation instructions;
    # no kingdom army size, opponent strength, or desired battle outcome is
    # disclosed.
    prompt = f"""
You are a strict evaluator for a medieval kingdom strategy game.

Evaluate this battle rallying cry harshly.

Most average rallying cries should score between 4 and 6 out of 10.
Start from 4/10 and only increase the score when the speech clearly earns it.

Penalise vague language, lazy speeches, generic phrases, unrealistic promises,
and speeches with no leadership, tactics, danger, sacrifice, enemy, army, or purpose.

Only award 8 or above if the rallying cry is specific, commanding, emotionally persuasive,
and strategically aware. A score of 9 or 10 should be very rare.

Score from 1 to 10:
- leadership_score
- inspiration_score
- practicality_score

Return JSON only with:
leadership_score
inspiration_score
practicality_score
rally_modifier
feedback

The rally_modifier must be between 0.92 and 1.08.

Rallying cry:
{rallying_cry}
"""

    try:
        # A missing client is converted into an exception so all configuration
        # and runtime failures use the same feature-specific fallback.
        client = get_gemini_client()#Initialises gemini client so that python can communicate with the gemini API
        if client is None:
            raise ValueError("Gemini API key is not configured")

        response = client.models.generate_content(
            # The model may be overridden through GEMINI_MODEL. If that setting
            # is missing or empty, the code uses Gemini 2.5 Flash.
            model=getattr(settings, "GEMINI_MODEL", None)
            or "gemini-2.5-flash",

            contents=prompt,

            # Structured output reduces free-form parsing uncertainty. Gemini is
            # instructed at both prompt and API-schema level to return JSON.
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema={
                    "type": "object", #Gemini should return a JSON object
                    "properties": { #Describes what fields should be inside the object
                        "leadership_score": {"type": "number"},
                        "inspiration_score": {"type": "number"},
                        "practicality_score": {"type": "number"},
                        "rally_modifier": {"type": "number"},
                        "feedback": {"type": "string"},
                    },
                    "required": [
                        "leadership_score",
                        "inspiration_score",
                        "practicality_score",
                        "rally_modifier",
                        "feedback",
                    ],
                },
            ),
        )

        # The SDK exposes the generated JSON as response.text. Invalid JSON
        # causes this workflow to use the conservative fallback below.
        data = safe_json_loads(response.text)
        if not data:
            raise ValueError("Invalid Gemini response")

        # Convert model-provided values to floats and clamp every score to the
        # application-controlled 1–10 range.
        data["leadership_score"] = clamp(
            float(data["leadership_score"]),
            1,
            10,
        )
        data["inspiration_score"] = clamp(
            float(data["inspiration_score"]),
            1,
            10,
        )
        data["practicality_score"] = clamp(
            float(data["practicality_score"]),
            1,
            10,
        )

        average_score = (
            data["leadership_score"]
            + data["inspiration_score"]
            + data["practicality_score"]
        ) / 3

        # Gemini's supplied rally_modifier is deliberately overwritten.
        #
        # Average score 1  → raw modifier 0.92
        # Average score 5  → raw modifier 1.00
        # Average score 10 → raw modifier 1.10, clamped to 1.08
        #
        # This limits direct AI influence on military strength to -8% through
        # +8%, regardless of the modifier Gemini attempted to return.
        data["rally_modifier"] = clamp(
            0.90 + (average_score / 10) * 0.20,
            0.92,
            1.08,
        )

        return data

    except Exception:
        # Missing configuration, network problems, invalid JSON, missing keys,
        # non-numeric scores, SDK exceptions, and other runtime failures all
        # produce the same predictable, mildly negative fallback.
        return {
            "leadership_score": 4,
            "inspiration_score": 4,
            "practicality_score": 4,
            "rally_modifier": 0.98,
            "feedback": (
                "The royal council could not fully assess this rallying cry, "
                "so only a minor effect was applied."
            ),
        }


def evaluate_event_response(event, player_response):
    """Evaluate a player's response to a kingdom crisis.

    Gemini receives the Event type, stored description, and player's submitted
    decree. It returns three qualitative category scores and written feedback.

    The returned category scores are converted to floats and clamped to 1–10.
    This helper recalculates ``ai_score`` as an unweighted average, but the
    event-response view later ignores that value and computes its own weighted
    score using the application's ``calculate_score()`` utility.

    Args:
        event: The unresolved Event being answered.
        player_response: The player's validated non-empty decree text.

    Returns:
        A dictionary containing:

        - ``empathy``;
        - ``leadership``;
        - ``practicality``;
        - ``ai_score``;
        - ``feedback``.

    On failure, every category and the returned average score are set to four.
    """
    # The prompt provides only the crisis details and player's response.
    # It does not expose the event's numerical effects, probability formula,
    # kingdom statistics, or effect-scaling formula.
    prompt = f"""
You are a strict royal council evaluating a ruler's response to a crisis
in a medieval kingdom strategy game.

Evaluate this response harshly. Most average responses should score between 4 and 6 out of 10.
Start from 4/10 and only increase the score when the response clearly earns it.

Penalise vague responses, unrealistic solutions, ignoring the specific crisis,
no practical implementation, cruelty without strategic purpose, kindness without planning,
and speeches that sound noble but do not solve the problem.

Only award 8 or above if the response is specific, realistic, morally aware,
strategically strong, and well suited to the crisis. A score of 9 or 10 should be rare.

Crisis type:
{event.event_type}

Crisis description:
{event.description}

Player response:
{player_response}

Score from 1 to 10:
- empathy
- leadership
- practicality

Return JSON only with:
empathy
leadership
practicality
ai_score
feedback
"""

    try:
        client = get_gemini_client()
        if client is None:
            raise ValueError("Gemini API key is not configured")

        response = client.models.generate_content(
            model=getattr(settings, "GEMINI_MODEL", None)
            or "gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema={
                    "type": "object",
                    "properties": {
                        "empathy": {"type": "number"},
                        "leadership": {"type": "number"},
                        "practicality": {"type": "number"},
                        "ai_score": {"type": "number"},
                        "feedback": {"type": "string"},
                    },
                    "required": [
                        "empathy",
                        "leadership",
                        "practicality",
                        "ai_score",
                        "feedback",
                    ],
                },
            ),
        )

        data = safe_json_loads(response.text)
        if not data:
            raise ValueError("Invalid Gemini response")

        # Scores are converted and bounded before any gameplay consumer receives
        # them. A model response outside the requested range cannot expand the
        # later event effect mitigation.
        data["empathy"] = clamp(
            float(data["empathy"]),
            1,
            10,
        )
        data["leadership"] = clamp(
            float(data["leadership"]),
            1,
            10,
        )
        data["practicality"] = clamp(
            float(data["practicality"]),
            1,
            10,
        )

        # Gemini's proposed ai_score is overwritten with an application-derived
        # arithmetic mean. The calling view subsequently calculates a different,
        # weighted score in which leadership has the greatest influence.
        data["ai_score"] = (
            data["empathy"]
            + data["leadership"]
            + data["practicality"]
        ) / 3

        return data

    except Exception:
        # A score of four produces a cautious but playable result. The view's
        # weighted calculation also resolves to four when all categories match.
        return {
            "empathy": 4,
            "leadership": 4,
            "practicality": 4,
            "ai_score": 4,
            "feedback": (
                "The royal council could not fully assess this response, "
                "so a cautious judgement was applied."
            ),
        }


def fallback_policy_advice(kingdom, policies, preview):
    """Generate deterministic premium policy advice without Gemini.

    This rule-based adviser is used whenever Gemini is unavailable or the
    response cannot be parsed. It examines validated policy values, current
    Kingdom state, and the deterministic policy preview.

    Args:
        kingdom: The current Kingdom being advised.
        policies: Validated ``PolicyForm.cleaned_data``.
        preview: Output from ``preview_policy_effects()``.

    Returns:
        A dictionary containing:

        - ``summary``;
        - ``risk``;
        - ``recommendation``;
        - ``preview``;
        - ``source="rules"``.

    The function has no database side effects. The dashboard view stores the
    returned dictionary in ``Kingdom.policy_advice``.
    """
    risks = []
    recommendations = []

    # Convert validated policy values to floats so comparisons remain
    # predictable regardless of their original numeric model/form type.
    tax_rate = float(policies["tax_rate"])
    agriculture = float(policies["agriculture_investment"])
    infrastructure = float(policies["infrastructure_investment"])
    military = float(policies["military_investment"])
    welfare = float(policies["welfare_investment"])

    # Heavy taxation is treated as a direct public-happiness risk.
    if tax_rate >= 35:
        risks.append("heavy taxation may damage happiness")
        recommendations.append(
            "reduce taxes or raise welfare before unrest spreads"
        )

    # Very low taxation is only considered dangerous when the current treasury
    # is also small relative to population.
    elif (
        tax_rate <= 10
        and kingdom.treasury < kingdom.population * 0.2
    ):
        risks.append("low taxation may leave the treasury exposed")
        recommendations.append(
            "raise taxes modestly until the treasury stabilises"
        )

    # Agricultural underinvestment is raised only when current food reserves
    # are below the population figure.
    if agriculture < 20 and kingdom.food < kingdom.population:
        risks.append("food reserves are vulnerable")
        recommendations.append(
            "increase agriculture investment to reduce famine pressure"
        )

    if infrastructure < 15:
        risks.append("weak infrastructure may slow long-term growth")
        recommendations.append(
            "restore infrastructure funding for future economic strength"
        )

    if welfare < 15 and kingdom.happiness < 45:
        risks.append("low welfare could deepen public anger")
        recommendations.append(
            "fund welfare until happiness recovers"
        )

    # Military underinvestment is flagged only while the kingdom is currently
    # visible as a warfare target.
    if military < 15 and kingdom.is_available_for_war():
        risks.append(
            "military readiness is weak while the realm is visible to rivals"
        )
        recommendations.append(
            "avoid war or increase military funding"
        )

    elif military >= 40:
        risks.append(
            "a military-heavy budget may starve domestic investment"
        )
        recommendations.append(
            "balance military spending with food or infrastructure"
        )

    # A balanced policy still returns a complete advice structure so the
    # dashboard can render the same fields regardless of source.
    if not risks:
        risks.append("no severe imbalance is visible")
        recommendations.append(
            "maintain a balanced policy unless a crisis appears"
        )

    return {
        "summary": (
            "The council sees your policy mix as workable but requiring "
            "careful balance."
        ),

        # At most the first two detected risks are included to keep the dashboard
        # advice concise.
        "risk": "; ".join(risks[:2]).capitalize() + ".",

        # Only the first recommendation is returned, so rule order determines
        # which recommendation receives priority when several risks exist.
        "recommendation": recommendations[0].capitalize() + ".",

        # The deterministic preview is retained in the stored JSON even though
        # the current dashboard displays only summary, risk, and recommendation.
        "preview": preview,

        # This source label distinguishes rule-based advice from Gemini advice.
        "source": "rules",
    }


def evaluate_policy_decision(kingdom, policies):
    """Generate premium policy advice from Gemini or deterministic rules.

    The function first calculates a non-persistent policy preview using backend
    simulation rules. Gemini receives that preview together with selected
    current Kingdom statistics and validated policy values.

    Gemini returns short strategic prose only. It does not change the Kingdom,
    consume a turn, or directly control any simulation value.

    Args:
        kingdom: The current premium Kingdom.
        policies: Validated ``PolicyForm.cleaned_data``.

    Returns:
        A dictionary containing:

        - ``summary``;
        - ``risk``;
        - ``recommendation``;
        - ``preview``;
        - ``source``.

    If the API call or parsing fails, ``fallback_policy_advice()`` returns a
    deterministic rule-based equivalent.
    """
    # The preview performs no writes and contains broad labels such as stable,
    # moderate risk, high risk, underfunded, or strong focus.
    preview = preview_policy_effects(kingdom, policies)

    # Gemini receives selected live state and the submitted policy allocation.
    # It is explicitly told not to reveal formulas or exact calculation details.
    prompt = f"""
You are a strict but concise royal advisor in a medieval strategy game.

Use only the information provided. Do not reveal exact formulas.
Give short strategic advice, not detailed calculations.

Current kingdom:
Food: {kingdom.food}
Treasury: {kingdom.treasury}
Happiness: {kingdom.happiness}
Stability: {kingdom.stability}
Army size: {kingdom.army_size}
Army quality: {kingdom.army_quality}
Territory: {kingdom.territory_count}
Wars won: {kingdom.wars_won}
Wars lost: {kingdom.wars_lost}

Policy choices:
Tax rate: {policies["tax_rate"]}
Agriculture: {policies["agriculture_investment"]}
Infrastructure: {policies["infrastructure_investment"]}
Military: {policies["military_investment"]}
Welfare: {policies["welfare_investment"]}

Simulation preview:
{preview}

Return JSON only with:
summary
risk
recommendation

Keep each field to one short sentence.
Do not give exact numbers or formulas.
"""

    try:
        client = get_gemini_client()
        if client is None:
            raise ValueError("Gemini API key is not configured")

        response = client.models.generate_content(
            model=getattr(settings, "GEMINI_MODEL", None)
            or "gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema={
                    "type": "object",
                    "properties": {
                        "summary": {"type": "string"},
                        "risk": {"type": "string"},
                        "recommendation": {"type": "string"},
                    },
                    "required": [
                        "summary",
                        "risk",
                        "recommendation",
                    ],
                },
            ),
        )

        data = safe_json_loads(response.text)
        if not data:
            raise ValueError("Invalid Gemini response")

        return {
            # Convert values to strings defensively and restrict their stored
            # length so unexpected verbose output cannot produce an excessively
            # large dashboard section.
            "summary": str(data["summary"])[:240],
            "risk": str(data["risk"])[:240],
            "recommendation": str(data["recommendation"])[:240],

            # Store the deterministic preview alongside the narrative advice.
            "preview": preview,

            # The source identifies successful Gemini-generated advice.
            "source": "gemini",
        }

    except Exception:
        # Policy advice remains available when Gemini is missing, unavailable,
        # or returns invalid data because the fallback uses local rules only.
        return fallback_policy_advice(
            kingdom,
            policies,
            preview,
        )