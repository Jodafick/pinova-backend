from __future__ import annotations

from notifications.notification_i18n import create_localized_notification

from monetization.models import PinBoost, PinPromoCampaign


def _campaign_headline(campaign: PinPromoCampaign) -> str:
    headline = (campaign.headline or '').strip()
    if headline:
        return headline[:80]
    if campaign.pin_id and getattr(campaign, 'pin', None):
        return (campaign.pin.title or 'Pin')[:80]
    return 'Campagne'


def notify_pin_promo_campaign_started(campaign: PinPromoCampaign) -> None:
    if not campaign.owner_id:
        return
    headline = _campaign_headline(campaign)
    create_localized_notification(
        recipient=campaign.owner,
        notification_type='system',
        title_fr='Campagne activée',
        message_fr=f'Votre campagne « {headline} » est en ligne.',
        action_url='/creator/campaigns',
        pin_id=campaign.pin_id,
        pin_slug=campaign.pin.slug if campaign.pin_id and getattr(campaign, 'pin', None) else None,
        metadata={
            'kind': 'campaign_started',
            'campaign_id': campaign.id,
            'delivery_mode': 'ws_and_push',
        },
    )


def notify_pin_boost_started(boost: PinBoost) -> None:
    if not boost.owner_id:
        return
    pin_title = (boost.pin.title if boost.pin_id and getattr(boost, 'pin', None) else 'Pin')[:80]
    create_localized_notification(
        recipient=boost.owner,
        notification_type='system',
        title_fr='Boost activé',
        message_fr=f'Votre boost sur « {pin_title} » est actif.',
        action_url='/creator/boost',
        pin_id=boost.pin_id,
        pin_slug=boost.pin.slug if boost.pin_id and getattr(boost, 'pin', None) else None,
        metadata={
            'kind': 'campaign_boost_started',
            'boost_id': boost.id,
            'delivery_mode': 'ws_and_push',
        },
    )
