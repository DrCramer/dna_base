import re
import unicodedata


def genetic_key(value: str | None) -> str:
    text = unicodedata.normalize("NFC", value or "").strip()
    text = text.translate(str.maketrans({character: "-" for character in "‐‑‒–—−"}))
    return re.sub(r"\s+", " ", text).casefold()


def genetic_number_parts(value: str, examination_no: str | None = None) -> tuple[str | None, int | None]:
    match = re.fullmatch(r"(\d{1,8})-(\d{1,4})", genetic_key(value))
    if examination_no:
        index = int(match[2]) if match and genetic_key(examination_no) == match[1] else None
        return examination_no.strip(), index
    if match and not 1900 <= int(match[2]) <= 2200:
        return match[1], int(match[2])
    return None, None


def control_kind(value: str | None) -> str | None:
    key = genetic_key(value)
    if key in {"ladder", "аллельная лестница"} or re.fullmatch(r"l\d+", key):
        return "ladder"
    if key in {"pc", "к+", "positive"}:
        return "pc"
    if key in {"nc", "к-", "negative"}:
        return "nc"
    return None
