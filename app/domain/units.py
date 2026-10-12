"""Exact rial/whole-gram arithmetic. No floats enter the domain."""
import re
from decimal import Decimal, ROUND_HALF_UP, localcontext

MAX_INT = 2**63 - 1
DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٫", "01234567890123456789.")


class DomainError(ValueError):
    pass


def integer(value: int, *, minimum: int = 0) -> int:
    if type(value) is not int or not minimum <= value <= MAX_INT:
        raise DomainError("مقدار صحیح خارج از محدوده است")
    return value


def normalized_name(value: str) -> str:
    return " ".join(value.translate(str.maketrans("يك", "یک")).split()).casefold()


def decimal_text(value: str) -> Decimal:
    if not isinstance(value, str):
        raise DomainError("ورودی باید متن باشد")
    value = value.strip().translate(DIGITS)
    if len(value) > 32 or not re.fullmatch(r"\d+(?:\.\d+)?", value):
        raise DomainError("عدد معتبر و غیرمنفی وارد کنید")
    return Decimal(value)


def toman_to_rial(value: str) -> int:
    d = decimal_text(value)
    if d.as_tuple().exponent < -1:
        raise DomainError("تومان حداکثر یک رقم اعشار دارد")
    with localcontext() as ctx:
        ctx.prec = 50
        return integer(int(d * 10))


def rial_to_toman(value: int) -> str:
    integer(value)
    whole, fraction = divmod(value, 10)
    return f"{whole:,}" + (f".{fraction}" if fraction else "")


def quantity(value: str, *, kind: str, unit: str, step: int) -> int:
    integer(step, minimum=1)
    d = decimal_text(value)
    factors = {("weight", "g"): 1, ("weight", "kg"): 1000,
               ("count", "count"): 1}
    try:
        factor = factors[(kind, unit)]
    except KeyError:
        raise DomainError("واحد نامعتبر است") from None
    with localcontext() as ctx:
        ctx.prec = 50
        base = d * factor
        if base != base.to_integral_value():
            raise DomainError("دقت مقدار بیش از واحد پایه است")
        q = integer(int(base), minimum=1)
    if q % step:
        raise DomainError("مقدار باید مضرب گام فروش باشد")
    return q


def display_weight(grams: int, unit: str) -> str:
    """Exact display without binary floats; zero stock is valid."""
    integer(grams)
    if unit == "g":
        return str(grams)
    if unit != "kg":
        raise DomainError("واحد نامعتبر است")
    whole, fraction = divmod(grams, 1000)
    return f"{whole}.{fraction:03d}"


def ratio_round(total: int, part: int, basis: int) -> int:
    integer(total)
    integer(part)
    integer(basis, minimum=1)
    with localcontext() as ctx:
        ctx.prec = 50
        return integer(int((Decimal(total) * part / basis).quantize(Decimal(1), rounding=ROUND_HALF_UP)))


def line_net(price: int, qty: int, basis: int, discount: int = 0) -> int:
    integer(qty, minimum=1)
    gross = ratio_round(price, qty, basis)
    integer(discount)
    if discount > gross:
        raise DomainError("تخفیف بیشتر از مبلغ ردیف است")
    return gross - discount


def return_share(original_total: int, original_qty: int, cumulative_qty: int,
                 previously_returned: int) -> int:
    integer(original_qty, minimum=1)
    integer(cumulative_qty, minimum=1)
    integer(previously_returned)
    if cumulative_qty > original_qty:
        raise DomainError("مرجوعی بیشتر از مقدار اصلی است")
    result = ratio_round(original_total, cumulative_qty, original_qty) - previously_returned
    return integer(result)
