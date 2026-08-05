from __future__ import annotations

OPENING_WITH_TECH = (
    "I noticed {company} recently launched a modern {product_label} " "built with {technologies}."
)

OPENING_WITHOUT_TECH = "I noticed {company} is building {product_label} for {audience}."

OPENING_MINIMAL = "I came across {company} and wanted to reach out."

COMPANY_SUMMARY_FULL = (
    "{company} appears to be a {category} company focused on {industry}. " "{description}"
)

COMPANY_SUMMARY_BASIC = "{company} is a {product_label} company. {description}"

MOBILE_OPPORTUNITY_NONE = (
    "I couldn't find a native mobile application, which may represent an "
    "opportunity to improve customer engagement."
)

MOBILE_OPPORTUNITY_PRESENT = (
    "{company} already appears to offer a mobile presence"
    "{store_clause}, so a complementary Flutter engagement may be less urgent."
)

TECH_SUMMARY_PRESENT = "Detected stack highlights include {technologies}."

TECH_SUMMARY_MISSING = "No clear technology signals were detected on the website."

QUALIFICATION_PASS = "Qualification passed with a score of {score}/100" "{reasons_clause}."

QUALIFICATION_FAIL = "Qualification did not pass (score {score}/100)" "{reasons_clause}."

QUALIFICATION_MISSING = "Qualification data was not available for this lead."

VALUE_PROP_FLUTTER = (
    "A Flutter-based mobile product could help {company} ship iOS and Android "
    "from one codebase while preserving the quality of the existing web experience."
)

VALUE_PROP_WITH_MOBILE = (
    "There may still be room to unify or modernize {company}'s mobile experience "
    "with a shared Flutter codebase across platforms."
)

VALUE_PROP_GENERIC = (
    "A focused technical partnership could help {company} accelerate product "
    "delivery and strengthen customer engagement."
)

CTA_FLUTTER = (
    "Would you be open to a short conversation about a Flutter mobile MVP " "for {company}?"
)

CTA_GENERIC = (
    "Would you be open to a brief call to explore how we could support "
    "{company}'s next product milestone?"
)

CTA_WITH_CONTACT = (
    "Would {contact_name} be open to a short conversation about next steps " "for {company}?"
)
