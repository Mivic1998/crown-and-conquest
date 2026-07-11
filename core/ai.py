import json

from django.conf import settings
from google import genai
from google.genai import types
from kingdoms.simulation import preview_policy_effects


def get_gemini_client():
    """Create the Gemini client lazily so the project still runs without an API key."""
    if not getattr(settings, "GEMINI_API_KEY", None):
        return None
    return genai.Client(api_key=settings.GEMINI_API_KEY)


def safe_json_loads(text):
    try:
        return json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return None


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def evaluate_rallying_cry(rallying_cry):
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
        client = get_gemini_client()
        if client is None:
            raise ValueError("Gemini API key is not configured")

        response = client.models.generate_content(
            model=getattr(settings, "GEMINI_MODEL", None) or "gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema={
                    "type": "object",
                    "properties": {
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

        data = safe_json_loads(response.text)
        if not data:
            raise ValueError("Invalid Gemini response")

        data["leadership_score"] = clamp(float(data["leadership_score"]), 1, 10)
        data["inspiration_score"] = clamp(float(data["inspiration_score"]), 1, 10)
        data["practicality_score"] = clamp(float(data["practicality_score"]), 1, 10)

        average_score = (
            data["leadership_score"]
            + data["inspiration_score"]
            + data["practicality_score"]
        ) / 3

        data["rally_modifier"] = clamp(0.90 + (average_score / 10) * 0.20, 0.92, 1.08)
        return data

    except Exception:
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
            model=getattr(settings, "GEMINI_MODEL", None) or "gemini-2.5-flash",
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

        data["empathy"] = clamp(float(data["empathy"]), 1, 10)
        data["leadership"] = clamp(float(data["leadership"]), 1, 10)
        data["practicality"] = clamp(float(data["practicality"]), 1, 10)
        data["ai_score"] = (data["empathy"] + data["leadership"] + data["practicality"]) / 3
        return data

    except Exception:
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
    """Rule-based premium advice used when Gemini is unavailable or fails."""
    risks = []
    recommendations = []

    tax_rate = float(policies["tax_rate"])
    agriculture = float(policies["agriculture_investment"])
    infrastructure = float(policies["infrastructure_investment"])
    military = float(policies["military_investment"])
    welfare = float(policies["welfare_investment"])

    if tax_rate >= 35:
        risks.append("heavy taxation may damage happiness")
        recommendations.append("reduce taxes or raise welfare before unrest spreads")
    elif tax_rate <= 10 and kingdom.treasury < kingdom.population * 0.2:
        risks.append("low taxation may leave the treasury exposed")
        recommendations.append("raise taxes modestly until the treasury stabilises")

    if agriculture < 20 and kingdom.food < kingdom.population:
        risks.append("food reserves are vulnerable")
        recommendations.append("increase agriculture investment to reduce famine pressure")

    if infrastructure < 15:
        risks.append("weak infrastructure may slow long-term growth")
        recommendations.append("restore infrastructure funding for future economic strength")

    if welfare < 15 and kingdom.happiness < 45:
        risks.append("low welfare could deepen public anger")
        recommendations.append("fund welfare until happiness recovers")

    if military < 15 and kingdom.is_available_for_war():
        risks.append("military readiness is weak while the realm is visible to rivals")
        recommendations.append("avoid war or increase military funding")
    elif military >= 40:
        risks.append("a military-heavy budget may starve domestic investment")
        recommendations.append("balance military spending with food or infrastructure")

    if not risks:
        risks.append("no severe imbalance is visible")
        recommendations.append("maintain a balanced policy unless a crisis appears")

    return {
        "summary": "The council sees your policy mix as workable but requiring careful balance.",
        "risk": "; ".join(risks[:2]).capitalize() + ".",
        "recommendation": recommendations[0].capitalize() + ".",
        "preview": preview,
        "source": "rules",
    }


def evaluate_policy_decision(kingdom, policies):
    """Return concise AI/rule-based advice for the premium policy advisor."""
    preview = preview_policy_effects(kingdom, policies)

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
            model=getattr(settings, "GEMINI_MODEL", None) or "gemini-2.5-flash",
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
                    "required": ["summary", "risk", "recommendation"],
                },
            ),
        )

        data = safe_json_loads(response.text)
        if not data:
            raise ValueError("Invalid Gemini response")

        return {
            "summary": str(data["summary"])[:240],
            "risk": str(data["risk"])[:240],
            "recommendation": str(data["recommendation"])[:240],
            "preview": preview,
            "source": "gemini",
        }

    except Exception:
        return fallback_policy_advice(kingdom, policies, preview)
