from __future__ import annotations

OPENING_WITH_PRODUCT = "I came across {company} — {product_hook}."

OPENING_WITHOUT_PRODUCT = "I came across {company} and spent a few minutes looking at what you're building."

OPENING_MINIMAL = "I came across {company} and wanted to reach out."

COMPANY_SUMMARY_FULL = (
    "{company} appears to be a {category} company focused on {industry}. " "{description}"
)

COMPANY_SUMMARY_BASIC = "{company} is a {product_label} company. {description}"

MOBILE_OPPORTUNITY_NONE = (
    "I couldn't find a mobile app for {company}, so I was curious whether "
    "mobile is already on your roadmap or still later."
)

MOBILE_OPPORTUNITY_PRESENT = (
    "{company} already appears to offer a mobile presence"
    "{store_clause}, so a complementary Flutter engagement may be less urgent."
)

# Internal notes for the model / debugging — never paste into outbound email as-is.
TECH_SUMMARY_PRESENT = "Internal stack signals (do not recite in email): {technologies}."

TECH_SUMMARY_MISSING = "No clear technology signals were detected on the website."

QUALIFICATION_PASS = "Qualification passed with a score of {score}/100" "{reasons_clause}."

QUALIFICATION_FAIL = "Qualification did not pass (score {score}/100)" "{reasons_clause}."

QUALIFICATION_MISSING = "Qualification data was not available for this lead."

VALUE_PROP_FLUTTER = (
    "I build Flutter apps and can help turn the existing product into a mobile "
    "experience without {company} needing another full-time engineer."
)

VALUE_PROP_WITH_MOBILE = (
    "I help teams ship or unify Flutter mobile apps so product engineering can "
    "stay focused on the core product."
)

VALUE_PROP_GENERIC = (
    "I help early-stage teams build and ship Flutter mobile apps without adding "
    "another full-time engineer — your web team can stay focused on the product."
)

CTA_FLUTTER = "Worth a quick chat about a Flutter mobile MVP, or is that off the table for now?"

CTA_GENERIC = "Is mobile something you're considering for {company}, or is it later?"

CTA_WITH_CONTACT = "Curious if mobile is on the roadmap — open to a short reply either way?"
