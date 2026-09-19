"""Shared word lists for spoken-form parsing."""

DIGIT_WORDS: dict[str, int] = {
    "zero": 0,
    "oh": 0,
    "o": 0,
    "nought": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "for": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
}

TEEN_WORDS: dict[str, int] = {
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
}

TENS_WORDS: dict[str, int] = {
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fourty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}

MAGNITUDE_WORDS: dict[str, int] = {
    "hundred": 100,
    "thousand": 1000,
    "million": 1_000_000,
}

UNIT_WORDS = {**DIGIT_WORDS, **TEEN_WORDS}
ALL_NUMBER_WORDS = {**UNIT_WORDS, **TENS_WORDS}

DECIMAL_MARKERS = {"point", "decimal"}

ORDINAL_WORDS: dict[str, int] = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
    "eleventh": 11,
    "twelfth": 12,
    "thirteenth": 13,
    "fourteenth": 14,
    "fifteenth": 15,
    "sixteenth": 16,
    "seventeenth": 17,
    "eighteenth": 18,
    "nineteenth": 19,
    "twentieth": 20,
    "thirtieth": 30,
}

MONTHS: dict[str, int] = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}

TRUE_PHRASES = {
    "yes",
    "yep",
    "yeah",
    "correct",
    "that's right",
    "thats right",
    "that is right",
    "affirmative",
    "i do",
    "we do",
    "true",
    "confirmed",
}

FALSE_PHRASES = {
    "no",
    "nope",
    "negative",
    "that's not right",
    "thats not right",
    "incorrect",
    "false",
    "i don't",
    "i do not",
    "we don't",
    "none",
    "not at all",
}
