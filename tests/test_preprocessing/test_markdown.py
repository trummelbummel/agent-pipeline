from __future__ import annotations

import logging
from pathlib import Path

import pytest

from compliance.models.claim import BookingData, is_nan_scalar
from compliance.preprocessing.markdown import MarkdownReader


def test_markdown_full_english(tmp_path: Path) -> None:
    path = tmp_path / "supporting1.md"
    path.write_text(
        "\n".join([
            "**Current date is: 2024-05-01**",
            "",
            "**Name**: Derek Kotze",
            "**Flight Number**: SA 1732",
            "**Airline**: South African Airways",
            "**Date**: 2024-03-05",
            "**Departure**: 9:15 local time",
            "**From**: Windhoek (WDH)",
            "**To**: Johannesburg (JNB)",
            "**Seat**: 16A",
            "**Class**: Economy",
        ]),
        encoding="utf-8",
    )

    result = MarkdownReader().read(path)

    assert result.current_date == "2024-05-01"
    assert result.name == "Derek Kotze"
    assert result.service == "SA 1732"
    assert result.operator == "South African Airways"
    assert result.departure == "9:15 local time"
    assert result.origin == "Windhoek (WDH)"
    assert result.destination == "Johannesburg (JNB)"
    assert result.seat == "16A"
    assert result.fare_type == "Economy"
    assert is_nan_scalar(result.booking_ref)
    assert is_nan_scalar(result.price)


def test_markdown_spanish_claim_22() -> None:
    path = Path("data/raw/claim 22/supporting1.md")
    if not path.is_file():
        pytest.skip("sample claim 22 not present")

    result = MarkdownReader().read(path)

    assert result.current_date == "2015-11-11"
    assert result.name == "José Juan Robledo Romero"
    assert result.booking_ref == "TRN-99563744"
    assert result.price == "€37"
    assert result.service == "ETN Primera Plus 1026"
    assert result.operator == "Primera Plus"
    assert result.origin == "Celaya, GTO"
    assert result.destination == "Guadalajara, JAL"
    assert result.seat == "10B (Primera Clase)"
    assert result.fare_type == "Regular"
    assert result.booked_on == "2015-10-10 14:32"
    assert is_nan_scalar(result.guests)


def test_markdown_sparse_current_date(tmp_path: Path) -> None:
    path = tmp_path / "sparse.md"
    path.write_text("**Current date is: 2020-01-02**\n", encoding="utf-8")

    result = MarkdownReader().read(path)

    assert result.current_date == "2020-01-02"
    for field in BookingData.model_fields:
        if field == "current_date":
            continue
        assert is_nan_scalar(getattr(result, field)), field


def test_markdown_underscore_keys_alias_to_booking_fields(tmp_path: Path) -> None:
    """Claim-6 style ``**current_date**`` / ``**booking_ref**`` must not be dropped."""
    path = tmp_path / "underscore.md"
    path.write_text(
        "\n".join([
            "**current_date**: 2017-07-27",
            "**name**: Marta Isabel Rojas Valbuena (partner)",
            "**booking_ref**: AV21930422",
            "**departure**: 2017-08-15 12:40 (local)",
            "**fare_type**: Economy",
            "**booked_on**: 2017-06-12 13:06",
        ]),
        encoding="utf-8",
    )

    result = MarkdownReader().read(path)

    assert result.current_date == "2017-07-27"
    assert result.name == "Marta Isabel Rojas Valbuena (partner)"
    assert result.booking_ref == "AV21930422"
    assert result.departure == "2017-08-15 12:40 (local)"
    assert result.fare_type == "Economy"
    assert result.booked_on == "2017-06-12 13:06"


def test_markdown_plain_unbolded_keys(tmp_path: Path) -> None:
    path = tmp_path / "plain.md"
    path.write_text(
        "\n".join([
            "Name: Naomi Feldman",
            "Booking Ref: TCK-89473319",
            "Price: $128",
            "Flight: SH4721",
            "Airline: SkyHopper",
        ]),
        encoding="utf-8",
    )

    result = MarkdownReader().read(path)

    assert result.name == "Naomi Feldman"
    assert result.booking_ref == "TCK-89473319"
    assert result.price == "$128"
    assert result.service == "SH4721"
    assert result.operator == "SkyHopper"


def test_markdown_unknown_key_dropped(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    path = tmp_path / "unknown.md"
    path.write_text(
        "\n".join([
            "**Name**: Alice",
            "**Mystery Field**: should drop",
        ]),
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING):
        result = MarkdownReader().read(path)

    assert result.name == "Alice"
    assert any("Mystery Field" in record.getMessage() for record in caplog.records)


def test_markdown_absent_fields_nan(tmp_path: Path) -> None:
    path = tmp_path / "name_only.md"
    path.write_text("**Name**: Only Name\n", encoding="utf-8")

    result = MarkdownReader().read(path)

    assert result.name == "Only Name"
    assert is_nan_scalar(result.current_date)
    assert is_nan_scalar(result.booking_ref)
    assert is_nan_scalar(result.cancellation)
