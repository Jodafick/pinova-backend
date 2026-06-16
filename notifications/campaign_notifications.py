from __future__ import annotations

from notifications.notification_i18n import create_localized_notification

from monetization.models import FotoBoost, FotoPromoCampaign


def _campaign_headline(campaign: FotoPromoCampaign) -> str:
    headline = (campaign.headline or '').strip()
    if headline:
        return headline[:80]
    if campaign.foto_id and getattr(campaign, 'foto', None):
        return (campaign.foto.title or 'Foto')[:80]
    return 'Campagne'


def notify_foto_promo_campaign_started(campaign: FotoPromoCampaign) -> None:
    if not campaign.owner_id:
        return
    headline = _campaign_headline(campaign)
    create_localized_notification(
        recipient=campaign.owner,
        notification_type='system',
        title_fr='Campagne activée',
        message_fr=f'Votre campagne « {headline} » est en ligne.',
        action_url='/creator/campaigns',
        foto_id=campaign.foto_id,
        foto_slug=campaign.foto.slug if campaign.foto_id and getattr(campaign, 'foto', None) else None,
        metadata={
            'kind': 'campaign_started',
            'campaign_id': campaign.id,
            'delivery_mode': 'ws_and_push',
        },
    )


def notify_foto_boost_started(boost: FotoBoost) -> None:
    if not boost.owner_id:
        return
    pin_title = (boost.foto.title if boost.foto_id and getattr(boost, 'foto', None) else 'Foto')[:80]
    create_localized_notification(
        recipient=boost.owner,
        notification_type='system',
        title_fr='Boost activé',
        message_fr=f'Votre boost sur « {pin_title} » est actif.',
        action_url='/creator/boost',
        foto_id=boost.foto_id,
        foto_slug=boost.foto.slug if boost.foto_id and getattr(boost, 'foto', None) else None,
        metadata={
            'kind': 'campaign_boost_started',
            'boost_id': boost.id,
            'delivery_mode': 'ws_and_push',
        },
    )
