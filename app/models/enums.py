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


class ReceiptSource(StrEnum):
    """Where the prices of a purchase came from."""

    SAMPLE = "sample"  # the demo's generated receipt
    AI = "ai"  # a photo read by Claude
    MANUAL = "manual"  # typed in by hand


class CorridorKind(StrEnum):
    """What a piece of the market's floor plan is."""

    AISLE = "aisle"  # shelves you walk along
    WALL = "wall"  # fridges or shelves against a wall
    ISLAND = "island"  # free-standing block: produce, promotions
    ENTRANCE = "entrance"  # where the route starts (no categories)
    CHECKOUT = "checkout"  # where the route ends (no categories)


class RouteStyle(StrEnum):
    """How the automatic zigzag walks a plan with more than one block of aisles."""

    COLUMN = "column"  # each aisle end to end, through the cross aisle
    BLOCK = "block"  # one block at a time
