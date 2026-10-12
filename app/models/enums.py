from enum import StrEnum


class ProductUnit(StrEnum):
    UNIT = "un"
    KILOGRAM = "kg"
    GRAM = "g"
    LITER = "l"
    MILLILITER = "ml"


class ShoppingListStatus(StrEnum):
    OPEN = "open"
    SHOPPING = "shopping"
    ARCHIVED = "archived"


class ShoppingListItemStatus(StrEnum):
    PENDING = "pending"
    CHECKED = "checked"
    NOT_FOUND = "not_found"
