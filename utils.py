TELEGRAM_MESSAGE_LIMIT = 4096
SAFE_MESSAGE_LIMIT = 3900


def split_long_message(text: str, limit: int = SAFE_MESSAGE_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    current = ""

    for paragraph in text.split("\n"):
        candidate = f"{current}\n{paragraph}".strip() if current else paragraph
        if len(candidate) <= limit:
            current = candidate
            continue

        if current:
            chunks.append(current)
            current = ""

        while len(paragraph) > limit:
            chunks.append(paragraph[:limit])
            paragraph = paragraph[limit:]

        current = paragraph

    if current:
        chunks.append(current)

    return chunks
