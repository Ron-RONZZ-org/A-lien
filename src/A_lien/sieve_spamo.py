"""Sieve script generation and merge logic for spam block rules.

Pure functions — no service dependency, fully testable in isolation.
"""

from __future__ import annotations

from typing import Any

# Marker comments used to identify the A-lien managed section in Sieve scripts
BEGIN_MARKER = "# A-lien spam rules begin"
END_MARKER = "# A-lien spam rules end"


def generate_spam_sieve(rules: list[str]) -> str:
    """Generate a Sieve if-block for a list of spam substring rules.

    Rules containing '@' are treated as full-email patterns (address :contains).
    Rules without '@' are treated as domain patterns (address :domain :contains).

    Args:
        rules: List of spam substring rules (lowercase)

    Returns:
        Complete Sieve fragment WITH markers, ready for injection
    """
    if not rules:
        return f"{BEGIN_MARKER}\n/* no spam rules */\n{END_MARKER}\n"

    # Partition: full-email vs domain-only patterns
    email_rules = [r for r in rules if "@" in r]
    domain_rules = [r for r in rules if "@" not in r]

    conditions: list[str] = []
    if email_rules:
        conds = ",\n    ".join(
            f'address :contains ["From"] "{r}"' for r in email_rules
        )
        conditions.append(conds)
    if domain_rules:
        conds = ",\n    ".join(
            f'address :domain :contains ["From"] "{r}"' for r in domain_rules
        )
        conditions.append(conds)

    all_conditions = ",\n    ".join(conditions)
    return (
        f"{BEGIN_MARKER}\n"
        f"if anyof (\n"
        f"    {all_conditions}\n"
        f") {{\n"
        f'    fileinto "Junk";\n'
        f"    stop;\n"
        f"}}\n"
        f"{END_MARKER}\n"
    )


def merge_spam_sieve(existing: str, new_spam_section: str) -> str:
    """Merge a generated spam section into an existing Sieve script.

    If markers already exist, replaces the content between them.
    If not, appends at the end with markers.

    Args:
        existing: Full existing Sieve script content
        new_spam_section: Generated section that INCLUDES markers

    Returns:
        Merged Sieve script
    """
    begin_idx = existing.find(BEGIN_MARKER)
    end_idx = existing.find(END_MARKER)

    if begin_idx != -1 and end_idx != -1:
        # Replace existing section
        end_of_end = end_idx + len(END_MARKER)
        return existing[:begin_idx] + new_spam_section + existing[end_of_end:]
    else:
        # Append at end
        return existing.rstrip() + "\n\n" + new_spam_section


__all__ = [
    "BEGIN_MARKER",
    "END_MARKER",
    "generate_spam_sieve",
    "merge_spam_sieve",
]
