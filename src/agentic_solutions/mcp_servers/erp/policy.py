"""The auto-approval policy: orders at or under the limit need no person."""


def format_zar(amount: float) -> str:
    """Whole rands with a thousands comma, e.g. R5,000."""
    return f"R{round(amount):,}"


def needs_person(total_zar: float, limit_zar: float) -> bool:
    return total_zar > limit_zar


def reason(total_zar: float, limit_zar: float) -> str:
    if needs_person(total_zar, limit_zar):
        return f"Over {format_zar(limit_zar)} needs approval"
    return f"Under {format_zar(limit_zar)}: approved by policy"
