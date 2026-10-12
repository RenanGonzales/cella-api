from decimal import Decimal

import pytest

from app.domain.stock import quantity_needed


@pytest.mark.parametrize(
    ("ideal", "current", "package", "expected"),
    [
        ("6", "3", "5", "5"),  # 3 kg missing, 5 kg package -> one package
        ("2", "0", "1", "2"),  # 2 liters missing, 1 liter carton -> two cartons
        ("12", "1", "6", "12"),  # 11 missing, pack of 6 -> two packs
        ("4", "4", "1", "0"),  # stock already at ideal
        ("4", "6", "1", "0"),  # stock above ideal
        ("1.5", "0.25", "0.5", "1.5"),  # fractional packages
    ],
)
def test_quantity_needed_rounds_up_to_whole_packages(ideal, current, package, expected):
    result = quantity_needed(Decimal(ideal), Decimal(current), Decimal(package))

    assert result == Decimal(expected)


def test_quantity_needed_rejects_non_positive_package():
    with pytest.raises(ValueError):
        quantity_needed(Decimal("2"), Decimal("0"), Decimal("0"))
