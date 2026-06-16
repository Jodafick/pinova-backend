"""
Textes juridiques par défaut pour Fotoce (version indicative, non substitut d'un avocat).
Surchargés en base via le modèle LegalDocument si renseignés.
"""

PRIVACY_FR = """POLITIQUE DE CONFIDENTIALITÉ — FOTOCE (version indicative)

Dernière mise à jour : 6 juin 2026

1. Responsable du traitement
Fotoce est un service de découverte et de partage de contenus visuels (« Fotos »), de tableaux (« boards ») et de stories. Les données sont traitées dans le cadre du fonctionnement de la plateforme et de l’exécution des services souscrits.

2. Données collectées
• Compte : identifiant, adresse e-mail, mot de passe chiffré, éventuellement nom d’affichage, biographie, langue préférée, date de naissance (obligatoire pour publier ; refus d’inscription si moins de 13 ans).
• Contenus : images, vidéos, titres, descriptions, tags publics et privés, tableaux, commentaires, mentions, signalements.
• Activité : likes, enregistrements, abonnements, consultations approximatives (statistiques créateur), notifications.
• Paiements : les transactions d’abonnement sont traitées par notre prestataire de paiement (ex. FedaPay) ; Fotoce ne conserve pas vos coordonnées bancaires complètes.
• Technique : journaux serveurs limités, tokens de notification push si vous les activez, consentement cookies (nécessaires / analytics PostHog).

3. Finalités
Fourniture du service, sécurité, modération, personnalisation du fil (dont sujets d’intérêt), lutte contre le spam et la fraude, obligations légales, support utilisateur et amélioration du produit (analytics uniquement avec consentement).

4. Fondements légaux
Exécution du contrat, intérêt légitime (sécurité, anti-abus), consentement lorsque requis (cookies analytics PostHog, notifications marketing si activées).

5. Partage et sous-traitants
• Prestataires d’infrastructure et d’hébergement.
• Prestataire de paiement pour les abonnements Plus / Pro.
• PostHog (UE) pour la mesure d’audience produit, si vous acceptez les cookies analytics.
• Outils optionnels de traduction automatique des textes courts (topics, commentaires selon les paramètres).
Aucune revente de vos données personnelles à des annonceurs en tant que telle ; les formules gratuites peuvent afficher des publicités sans profilage comportemental invasif tel que décrit dans nos engagements produit.

6. Durées de conservation
Tant que le compte est actif, puis durées légales applicables après suppression ou anonymisation lorsque possible. Suppression de compte : délai de grâce de 30 jours avant purge définitive (e-mail de confirmation).

7. Droits des personnes (UE / RGPD)
Accès, rectification, suppression, limitation, opposition, portabilité. Export de vos données : Paramètres → « Exporter mes données » ou `POST /api/account/export-data/` — archive ZIP JSON (profil, Fotos, commentaires, notifications, abonnements, tips) envoyée par e-mail (lien valable 24 h). Consentement cookies : bannière web ou `POST /api/account/consent/`. Contact via les canaux prévus dans l’application ou le support.

8. Mineurs
Inscription refusée si l’âge déclaré est inférieur à 13 ans. Comptes de 13 à 17 ans : consultation et interactions possibles, publication de contenu restreinte. Les parents doivent encadrer l’usage des plus jeunes utilisateurs.

9. Cookies
Cookies strictement nécessaires (session, sécurité) toujours actifs. Cookies analytics (PostHog) désactivés par défaut jusqu’à votre choix dans la bannière cookies.

10. Transferts hors UE
Si des prestataires sont situés hors Union européenne, des garanties adaptées (clauses contractuelles types ou équivalent) sont recherchées.

11. Réclamations
Vous pouvez saisir l’autorité de protection des données compétente en cas de différend.

---

REVUE AVOCAT (placeholder — à compléter avant go-live définitif)
• Cabinet / avocat référent : [À RENSEIGNER]
• Date de revue : [À RENSEIGNER — cible : juin 2026]
• Périmètre validé : politique de confidentialité, CGU, bannière cookies, export RGPD, mineurs, suppression 30 j.
• Réserve(s) éventuelle(s) : [AUCUNE / À PRÉCISER]
• Signataire : [Nom, titre] — Statut : EN ATTENTE DE REVUE FORMELLE"""

PRIVACY_EN = """PRIVACY POLICY — FOTOCE (informational draft)

Last updated: 6 June 2026

1. Data controller
Fotoce is a visual discovery platform for Fotos, boards and stories. Data is processed to run the service and deliver paid plans.

2. Data we collect
• Account: username, email, hashed password, optional display name, bio, preferred language, birth date (required to publish; registration rejected under age 13).
• Content: images, videos, titles, descriptions, public and private tags, boards, comments, mentions, moderation reports.
• Activity: likes, saves, follows, approximate view statistics for creators, notifications.
• Payments: subscriptions are handled by our payment provider (e.g. FedaPay); we do not store full card numbers.
• Technical logs, optional web push subscription data, cookie consent choices (necessary / PostHog analytics).

3. Purposes
Provide the platform, secure accounts, moderate content, personalize feeds (including topics of interest), fight spam and fraud, comply with law, operate support, product analytics only with consent.

4. Legal bases
Contract performance, legitimate interests (security, anti-abuse), consent where applicable (PostHog analytics cookies).

5. Sharing
Infrastructure providers, payment processor for Plus/Pro, PostHog (EU) for product analytics if you opt in, optional machine-translation tooling for short text. No sale of personal data to advertisers as described on our Premium page commitments.

6. Retention
While your account exists, then statutory periods or anonymization where feasible. Account deletion: 30-day grace period before permanent purge (confirmation email).

7. Your rights
Access, correction, deletion, restriction, objection, portability. Data export: Settings → “Download my data” or `POST /api/account/export-data/` — JSON ZIP (profile, Fotos, comments, notifications, subscriptions, tips) emailed with a 24-hour download link. Cookie consent: web banner or `POST /api/account/consent/`. Contact routes available in-product.

8. Minors
Registration rejected if declared age is under 13. Accounts aged 13–17 may browse and interact but cannot publish content. Guardians should supervise younger users.

9. Cookies
Strictly necessary cookies (session, security) always active. Analytics cookies (PostHog) off by default until you choose in the cookie banner.

10. International transfers
Where providers are outside your region, we seek appropriate safeguards.

11. Complaints
You may contact your local data-protection authority.

---

LEGAL COUNSEL REVIEW (placeholder — complete before final go-live)
• Referral counsel / firm : [TBD]
• Review date : [TBD — target June 2026]
• Scope validated : privacy policy, terms, cookie banner, GDPR export, minors, 30-day deletion grace.
• Outstanding notes : [NONE / TBD]
• Signatory : [Name, title] — Status : PENDING FORMAL REVIEW"""

TERMS_FR = """CONDITIONS GÉNÉRALES D’UTILISATION — FOTOCE (version indicative)

Dernière mise à jour : 6 juin 2026

1. Objet
Les présentes conditions régissent l’accès et l’utilisation de Fotoce (site et API associées).

2. Compte et sécurité
Vous devez fournir des informations exactes, garder vos identifiants confidentiels et signaler tout accès non autorisé.

3. Contenus utilisateurs
Vous conservez vos droits sur vos contenus. Vous concedez à Fotoce une licence non exclusive mondiale pour héberger, afficher et distribuer vos contenus sur la plateforme et pour les fonctionnalités associées (partage, API interne de modération, sauvegarde).
Interdits : contenus illégaux, haineux, violents non contextuels, atteinte à la vie privée d’autrui sans consentement, spam, piratage, scraping abusif, contournement des limites du plan gratuit ou payant.

4. Plans Free, Plus et Pro
Les quotas (tags privés, tableaux, collaborateurs par board, téléchargements, GIF commentaires, publicités désactivées, etc.) sont ceux présentés sur la page Plans & Premium et peuvent évoluer avec préavis raisonnable. Les paiements sont finalisés par un prestataire tiers ; aucun remboursement n’est garanti hors politique du prestataire et loi applicable.

5. Collaboration sur les boards
Le créateur du board est propriétaire aux fins des limites d’offre ; les invitations à collaborer doivent être acceptées par l’invité. Fotoce peut retirer l’accès en cas de violation des règles.

6. Modération
Une modération automatique et manuelle peut filtrer, masquer ou supprimer tout contenu signalé ou détecté comme non conforme. Les décisions graves peuvent mener à la suspension ou suppression du compte.

7. Propriété intellectuelle de Fotoce
Marques, logos, design et logiciel Fotoce sont protégés. Aucune licence n’est accordée sur ces éléments au-delà de l’usage normal du service.

8. Limitation de responsabilité
Le service est fourni « en l’état » dans les limites autorisées par la loi. Fotoce ne saurait être tenue dommage-intérêt pour des pertes indirectes sauf disposition impérative contraire.

9. Résiliation
Vous pouvez supprimer votre compte ; nous pouvons suspendre ou clôturer tout compte en cas de violation des CGU.

10. Droit applicable et litiges
Le droit applicable est celui désigné par Fotoce conformément aux règles de conflict de lois pertinentes pour votre résidence lorsque une consommation existe ; les juridictions compétentes suivent les règles du droit français ou du pays de consommation le cas échéant (à adapter avec un conseil juridique)."""

TERMS_EN = """TERMS OF SERVICE — FOTOCE (informational draft)

Last updated: 6 June 2026

1. Scope
These terms govern your use of Fotoce (web properties and APIs).

2. Accounts
Provide accurate details, safeguard credentials and notify us of unauthorized access.

3. Your content
You retain ownership. You grant Fotoce a non-exclusive worldwide licence to host, display and technically process your uploads for the functioning of Fotos, boards, stories, moderation and sharing tools.
You must not publish illegal material, credible threats, harassment, non-consensual intimate imagery, privacy violations, abusive scraping, malicious code, or circumvent plan limits.

4. Plans Free, Plus & Pro
Features and quotas mirror the Premium/plan descriptions and may evolve with reasonable notice. Payments flow through external processors ; refunds follow processor rules and mandatory consumer law where it applies.

5. Collaborative boards
Quotas attach to the board owner ; collaborators join only after accepting an invitation. Access may be removed for misconduct.

6. Moderation
We may hide or delete content and suspend accounts consistent with policies and notices.

7. Fotoce intellectual property
Branding and software remain ours except for ordinary end-user licence to operate the UI.

8. Disclaimer
Within legal limits Fotoce provides the service « as-is » ; indirect damages exclusions apply where permissible.

9. Termination
You may delete your account ; we may terminate for breach.

10. Governing law
Choose governing law/jurisdiction aligned with Fotoce operating base and mandatory consumer protections in your region (verify with counsel)."""

CONTACT_FR = """Une question sur votre compte, une idée d’amélioration ou un souci technique ? Notre équipe lit tous les messages.

Indiquez si possible votre nom d’utilisateur Fotoce et votre navigateur (ou appareil). Pour une demande liée aux données personnelles, précisez « données personnelles » dans l’objet de votre message.

Nous répondons en général sous trois à cinq jours ouvrés."""

CONTACT_EN = """Questions about your account, product feedback, or a technical issue? Our team reads every message.

Please include your Fotoce username and browser (or device) when relevant. For privacy-related requests, include “privacy request” in the subject line.

We usually reply within three to five business days."""


def default_title(slug: str, lang: str) -> str:
    lang = (lang or 'fr').lower().split('-')[0]
    if slug == 'privacy':
        return 'Privacy policy' if lang == 'en' else 'Politique de confidentialité'
    if slug == 'terms':
        return 'Terms of service' if lang == 'en' else "Conditions générales d'utilisation"
    if slug == 'contact':
        return 'Contact us' if lang == 'en' else 'Nous contacter'
    return 'Fotoce'


def default_body(slug: str, lang: str) -> str:
    lang = (lang or 'fr').lower().split('-')[0]
    if slug == 'privacy':
        return PRIVACY_EN if lang == 'en' else PRIVACY_FR
    if slug == 'terms':
        return TERMS_EN if lang == 'en' else TERMS_FR
    if slug == 'contact':
        return CONTACT_EN if lang == 'en' else CONTACT_FR
    return ''
