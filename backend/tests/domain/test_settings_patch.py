"""Partial notification settings (ADR-0021): KEEP vs None vs value; the merged result is
what gets validated."""

from datetime import time

import pytest

from tristhana.domain.notifications import (
    DEFAULTS,
    InvalidSettings,
    NotificationPatch,
    QuietHours,
    StoredSettings,
    apply_patch,
    check_settings,
    effective,
)


def test_null_columns_mean_the_defaults() -> None:
    assert effective(StoredSettings(), DEFAULTS) == DEFAULTS


def test_only_sent_fields_change() -> None:
    stored = StoredSettings(moon_at=time(7), practice_on=True)

    patched = apply_patch(stored, NotificationPatch(moon_offsets=frozenset({1})))

    assert patched == StoredSettings(moon_offsets=frozenset({1}), moon_at=time(7), practice_on=True)
    assert NotificationPatch(moon_offsets=frozenset({1})).columns() == {"moon_offsets": {1}}


def test_none_goes_back_to_the_default_and_quiet_is_a_pair() -> None:
    stored = StoredSettings(moon_at=time(7), quiet_start=time(23), quiet_end=time(6))

    patched = apply_patch(stored, NotificationPatch(moon_at=None, quiet=None))

    assert (patched.moon_at, patched.quiet_start, patched.quiet_end) == (None, None, None)
    assert effective(patched, DEFAULTS).quiet == DEFAULTS.quiet


def test_the_merged_result_is_checked_against_stored_reminders() -> None:
    stored = StoredSettings(practice_on=True, practice_at=time(20))
    swallowing = NotificationPatch(quiet=QuietHours(time(19), time(7)))

    with pytest.raises(InvalidSettings):
        check_settings(effective(apply_patch(stored, swallowing), DEFAULTS))
    off = StoredSettings(practice_on=False, practice_at=time(20), moon_offsets=frozenset())
    check_settings(effective(apply_patch(off, swallowing), DEFAULTS))
