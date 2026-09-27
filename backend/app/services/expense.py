import re
import unicodedata

from fastapi import HTTPException, status


def validate_expense_category(category: str) -> None:
    normalized = " ".join(
        "".join(
            character
            for character in unicodedata.normalize("NFKD", category.casefold())
            if not unicodedata.combining(character)
        ).split()
    )
    if re.search(r"\b(nhan cong|labor|tien cong|wages?)\b", normalized):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Labor cost belongs in labor_records, not expenses",
        )
