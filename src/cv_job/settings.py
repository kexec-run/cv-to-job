"""Small, read-only checks for documented preferences; not an ATS policy engine."""

import math
import re

import yaml

from cv_job.config import WorkspaceConfig


def settings_issues(config: WorkspaceConfig) -> list[dict]:
    issues = []
    for file_key in ("preferences", "ats_answers"):
        path = config.paths.get(file_key)
        if path is None or not path.is_file():
            continue  # The path audit reports this separately.

        def fail(key, message, file_key=file_key):
            # Never include supplied values or YAML exception excerpts in diagnostics.
            issues.append({"type": "invalid_workspace_settings", "file": file_key,
                           "field": key, "message": message})

        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError):
            fail("<document>", "could not read valid YAML")
            continue
        if not isinstance(data, dict):
            fail("<document>", "must be a mapping")
            continue

        def mapping(parent, key, prefix=""):
            value = parent.get(key, {})
            if not isinstance(value, dict):
                fail(prefix + key, "must be a mapping")
                return {}
            return value

        def choice(parent, key, options, prefix=""):
            if key in parent and (not isinstance(parent[key], str) or parent[key] not in options):
                fail(prefix + key, "must be one of: " + ", ".join(sorted(options)))

        def strings(parent, key, prefix="", options=None):
            value = parent.get(key, [])
            if (not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value)
                    or (options is not None and any(item not in options for item in value))):
                fail(prefix + key, "must be a list of valid non-empty strings")
                return []
            if len(value) != len(set(value)):
                fail(prefix + key, "must not contain duplicates")
            return value

        if file_key == "preferences":
            choice(data, "submission", {"review_before_submit", "auto_submit"})
            strings(data, "target_families")
            for key in ("remote", "hybrid", "onsite", "relocation", "travel", "night_shifts"):
                # Keep older workspace choices readable without rewriting personal files.
                if key == "remote" and isinstance(data.get(key), bool):
                    continue
                if key == "relocation" and isinstance(data.get(key), dict):
                    continue  # Older workspaces use location-specific relocation rules.
                choice(data, key, {"accept", "decline", "ask", "accept_if_posting_requires"})
            kinds = mapping(data, "job_kinds")
            options = {"full_time", "part_time", "contract", "temporary", "internship", "apprenticeship"}
            accepted = strings(kinds, "accepted", "job_kinds.", options)
            excluded = strings(kinds, "excluded", "job_kinds.", options)
            if set(accepted) & set(excluded):
                fail("job_kinds", "accepted and excluded must not overlap")
            choice(kinds, "unlisted", {"ask", "decline"}, "job_kinds.")
            locations = mapping(data, "locations")
            for key in ("countries", "cities"):
                strings(locations, key, "locations.")
            choice(locations, "outside_preferences", {"ask", "decline"}, "locations.")
            salary = mapping(data, "salary")
            minimum = salary.get("minimum")
            if minimum is not None and (type(minimum) not in (int, float)
                                        or (type(minimum) is float and not math.isfinite(minimum))
                                        or minimum < 0):
                fail("salary.minimum", "must be a nonnegative finite number or null")
            currency = salary.get("currency")
            if currency is not None and (not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency)):
                fail("salary.currency", "must be a three-letter uppercase currency code or null")
            if salary.get("period") is not None:
                choice(salary, "period", {"annual", "monthly", "hourly"}, "salary.")
            if minimum is not None and (currency is None or salary.get("period") is None):
                fail("salary", "currency and period are required when minimum is supplied")
            notice = data.get("notice_period_days")
            if notice is not None and (type(notice) is not int or notice < 0):
                fail("notice_period_days", "must be a nonnegative integer or null")
        else:
            mapping(data, "answers")
            authorization = mapping(data, "work_authorization")
            countries = mapping(authorization, "by_country", "work_authorization.")
            for country, value in countries.items():
                # Avoid putting arbitrary country keys (or mistaken secrets) into output.
                if not isinstance(country, str) or not country or not isinstance(value, dict):
                    fail("work_authorization.by_country", "must map country names to answer mappings")
                    continue
                for key in ("authorized", "sponsorship_required_now", "sponsorship_required_future"):
                    if value.get(key) is not None and type(value[key]) is not bool:
                        fail("work_authorization.by_country", "eligibility answers must be boolean or null")
            demographics = data.get("demographics", {})
            if isinstance(demographics, str):
                choice(data, "demographics", {"prefer_not_to_answer", "prefer_not_to_disclose", "ask"})
            else:
                demographics = mapping(data, "demographics")
                for key in ("gender", "race_ethnicity", "disability", "veteran_status"):
                    choice(demographics, key, {"prefer_not_to_disclose", "ask"}, "demographics.")
                choice(demographics, "if_decline_option_missing", {"ask", "leave_blank"}, "demographics.")
            consent = mapping(data, "consent")
            for key in ("application_data_processing", "privacy_notice_acknowledgment", "future_opportunities",
                        "marketing", "optional_sms", "background_check"):
                choice(consent, key, {"ask", "accept", "decline"}, "consent.")
            choice(consent, "accuracy_certification", {"review_before_accepting", "ask"}, "consent.")
            choice(consent, "combined_or_unclear_consent", {"ask", "decline"}, "consent.")
            choice(data, "unknown_required_answer", {"ask"})
            choice(data, "unknown_optional_answer", {"leave_blank", "ask"})
    return issues
