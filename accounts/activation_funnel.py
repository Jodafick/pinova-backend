"""État funnel d'activation créateur (tutoriel, jalons, célébrations)."""

ALLOWED_MILESTONES = frozenset(
    {
        'first_foto_published',
        'first_follow_obtained',
        'first_story_published',
        'first_comment_posted',
        'first_tip_received',
        'first_contest_joined',
        'creator_discovery_done',
    }
)

ALLOWED_TUTORIAL = frozenset({'completed', 'dismissed'})


def normalize_activation_funnel_json(raw) -> dict:
    if not isinstance(raw, dict):
        return {}
    out: dict = {}
    tutorial = raw.get('welcomeCreateTutorial')
    if tutorial in ALLOWED_TUTORIAL:
        out['welcomeCreateTutorial'] = tutorial
    if raw.get('firstPinCelebrationSeen') is True:
        out['firstPinCelebrationSeen'] = True
    milestones = raw.get('milestones')
    if isinstance(milestones, list):
        cleaned = []
        seen = set()
        for item in milestones:
            slug = str(item or '').strip()
            if slug in ALLOWED_MILESTONES and slug not in seen:
                seen.add(slug)
                cleaned.append(slug)
        if cleaned:
            out['milestones'] = cleaned
    return out


def merge_activation_funnel_json(current: dict, patch: dict) -> dict:
    base = normalize_activation_funnel_json(current if isinstance(current, dict) else {})
    incoming = normalize_activation_funnel_json(patch if isinstance(patch, dict) else {})
    merged = dict(base)
    if 'welcomeCreateTutorial' in incoming:
        merged['welcomeCreateTutorial'] = incoming['welcomeCreateTutorial']
    if incoming.get('firstPinCelebrationSeen'):
        merged['firstPinCelebrationSeen'] = True
    milestones = list(merged.get('milestones') or [])
    seen = set(milestones)
    for slug in incoming.get('milestones') or []:
        if slug not in seen:
            seen.add(slug)
            milestones.append(slug)
    if milestones:
        merged['milestones'] = milestones
    return merged
