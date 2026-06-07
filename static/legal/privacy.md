# MatchForge Privacy Policy

**Version:** 2026-06-07  
**Effective:** June 7, 2026

MatchForge is built **privacy-first**. This policy explains what we collect, where it lives, and your rights.

## 1. Our Privacy Principles

- **Your data is yours** — we do not sell or rent personal information
- **Local-first when self-hosted** — you control your server and database
- **Minimal collection** — we only store what the toolbox needs to function
- **Transparent AI processing** — you consent before images are analyzed
- **Deletion rights** — you can remove your data

## 2. What We Store

Depending on how you use MatchForge, we may store:

| Data | Purpose |
|------|---------|
| Email address | Account sign-in and verification |
| Profile settings | Gender, goals, optional bio, handle, avatar/selfie you provide |
| Preference vector | Personalized ranking weights generated from your onboarding |
| Screenshots you upload | Vision extraction, trust scoring, ranking |
| Analysis results | Compatibility scores, trust badges, explanations, notes |
| Evidence & agent inputs | Optional notes, chat snips, images you attach for vetting |
| Referral codes | Attribution for token rewards |
| Policy acceptance timestamp | Proof you agreed to Terms and this Privacy Policy |

We do **not** intentionally collect government ID, financial data, or precise geolocation unless you type it into optional profile fields.

## 3. Where Data Lives

### Self-hosted deployment
Data is stored in **your** PostgreSQL database and file storage on **your** server/container. Network calls to AI providers only occur if you configure API keys.

### Hosted deployment (match-forge.com)
Data is stored in your account on our managed infrastructure (database and application storage). When AI features are enabled, **screenshots and text may be sent to configured AI providers** (currently xAI Grok) for analysis. We do not use your data to train third-party models.

## 4. AI Processing and Consent

When you upload screenshots, avatars, selfies, or example profiles, you **consent** to automated analysis including:

- Text and image extraction
- Trust, authenticity, and catfish-risk scoring
- Personalized compatibility ranking

You can stop uploading at any time. Deleting profiles or your account removes associated stored data from your instance.

## 5. Social Enrichment

If enabled, MatchForge may retrieve **publicly available** web or social information to help vet profiles. We do not access private accounts, DMs, or paywalled content on your behalf.

## 6. What We Do Not Do

- We do **not** sell your personal information
- We do **not** share your screenshots with other users (unless **you** explicitly use the share feature)
- We do **not** publish ranked lists of real people
- We do **not** guarantee that cloud AI providers retain zero logs — review their policies if you use hosted AI

## 7. Your Rights (Including Canada / PIPEDA)

If you are in Canada, you have rights under the **Personal Information Protection and Electronic Documents Act (PIPEDA)**, including:

- **Access** — ask what personal information we hold about you
- **Correction** — update inaccurate account or profile settings
- **Deletion** — request removal of your account and associated data
- **Withdraw consent** — stop using the service; deletion requests honored subject to legal retention limits

To exercise these rights on a hosted deployment, contact the operator via the email on your account or the site footer. Self-hosted operators handle requests directly.

## 8. Retention

We retain data while your account is active and as needed to operate the service. You may delete individual profile workups from the dashboard. Account deletion removes your user profile, rankings, and uploads associated with your account.

## 9. Security

We use industry-standard practices (HTTPS, hashed tokens, access controls). No system is perfectly secure — protect your credentials and self-hosted secrets.

## 10. Children

MatchForge is for adults (18+). We do not knowingly collect data from minors.

## 11. Changes

We may update this policy. A new version number will require re-acceptance where applicable.

## 12. Contact

Privacy questions: the operator listed on your deployment's domain or GitHub repository.

---

*By clicking "I Agree", you confirm you have read and accept this Privacy Policy and our Terms of Service.*