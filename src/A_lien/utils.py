"""Utility functions for A-lien.

Provides helpers for:
- Contact normalization (name splitting, email dedup)
- VCF import/export helpers (supplementary to service layer)
"""

from __future__ import annotations


def split_full_name(plena_nomo: str) -> tuple[str, str]:
    """Split a full name into given and family name.

    Simple heuristic: last word = family name, rest = given name.

    Args:
        plena_nomo: Full name string

    Returns:
        (given_name, family_name) tuple
    """
    parts = plena_nomo.strip().split()
    if not parts:
        return ("", "")
    if len(parts) == 1:
        return (parts[0], "")
    return (" ".join(parts[:-1]), parts[-1])


def normalize_email(email: str) -> str:
    """Normalize an email address to lowercase.

    Args:
        email: Raw email address

    Returns:
        Lowercase, stripped email
    """
    return email.strip().lower()


def format_phone(phone: str) -> str:
    """Normalize a phone number by removing non-digit characters.

    Keeps leading + for international prefix.

    Args:
        phone: Raw phone string

    Returns:
        Cleaned phone number
    """
    if not phone:
        return ""
    phone = phone.strip()
    if phone.startswith("+"):
        return "+" + "".join(ch for ch in phone[1:] if ch.isdigit())
    return "".join(ch for ch in phone if ch.isdigit())


__all__ = [
    "split_full_name",
    "normalize_email",
    "format_phone",
]
