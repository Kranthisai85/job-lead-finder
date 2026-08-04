from app.validation.types import CompanyValidationResult, ValidationReport, ValidationSummary


def format_company_section(result: CompanyValidationResult) -> str:
    technologies = "\n".join(result.technologies) if result.technologies else "None"
    email_pattern = result.email_pattern or "None"
    lines = [
        "=========================================================",
        "Company",
        "=========================================================",
        "",
        "Name:",
        result.name,
        "",
        "Website:",
        result.website,
        "",
        "Website Reachable:",
        "YES" if result.website_reachable else "NO",
        "",
        "Technologies:",
        technologies,
        "",
        "Mobile App:",
        "YES" if result.mobile_app else "NO",
        "",
        "Play Store:",
        "YES" if result.play_store else "NO",
        "",
        "App Store:",
        "YES" if result.app_store else "NO",
        "",
        "Qualification:",
        "PASS" if result.qualification_pass else "FAIL",
        "",
        "Qualification Score:",
        str(result.qualification_score),
        "",
        "Contact Emails Found:",
        str(result.contact_emails_found),
        "",
        "Decision Makers:",
        str(result.decision_makers),
        "",
        "Email Pattern:",
        email_pattern,
        "",
        "Lead Score:",
        f"{result.lead_score:.0f}",
        "",
    ]
    if result.errors:
        lines.extend(["Errors:", *[f"- {error}" for error in result.errors], ""])
    return "\n".join(lines)


def format_summary(summary: ValidationSummary) -> str:
    return "\n".join(
        [
            "=========================================================",
            "Summary",
            "=========================================================",
            "",
            "Companies Processed:",
            str(summary.companies_processed),
            "",
            "Reachable:",
            str(summary.reachable),
            "",
            "Qualified:",
            str(summary.qualified),
            "",
            "Mobile Apps:",
            str(summary.mobile_apps),
            "",
            "Emails Found:",
            str(summary.emails_found),
            "",
            "Technology Detection Success:",
            str(summary.technology_detection_success),
            "",
            "Good Leads:",
            str(summary.good_leads),
            "",
            "Average Lead Score:",
            f"{summary.average_lead_score:.1f}",
            "",
        ]
    )


def render_report(report: ValidationReport) -> str:
    sections = [format_company_section(result) for result in report.results]
    sections.append(format_summary(report.summary))
    return "\n".join(sections)
