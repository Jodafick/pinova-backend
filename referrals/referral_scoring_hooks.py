"""
Pont concours fotos → scoring referral (filleul actif sur le contenu).
Appelé depuis contests.services.track_contest_interaction après une interaction valide.
"""

from __future__ import annotations


def on_contest_interaction_for_referral(
    *,
    foto,
    actor,
    contest_settings,
    interaction_valid: bool,
    trust_score: float,
    pin_contest_delta: float,
) -> None:
    if not interaction_valid or pin_contest_delta <= 0:
        return
    if not getattr(actor, 'id', None):
        return
    if actor.id == foto.author_id:
        return
    from referrals.services import award_engagement_from_referee_to_referrer

    award_engagement_from_referee_to_referrer(
        referee=actor,
        contest=contest_settings,
        trust_score=float(trust_score or 1.0),
        foto_id=getattr(pin, 'id', None),
    )
