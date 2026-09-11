def format_inr(amount: int) -> str:
    sign = "-" if amount < 0 else ""
    digits = str(abs(amount))
    if len(digits) <= 3:
        return f"{sign}₹{digits}"
    result = digits[-3:]
    rest = digits[:-3]
    while rest:
        result = rest[-2:] + "," + result
        rest = rest[:-2]
    return f"{sign}₹{result}"
