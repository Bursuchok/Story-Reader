
import json
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent

INBOX = ROOT / "New Stories"
PUBLISHED = ROOT / "Published Stories"
CATALOG = ROOT / "catalog.json"

METADATA_MARKER = "<!-- STORY-METADATA -->"
CONTENT_MARKER = "<!-- STORY-CONTENT -->"

RAW_BASE_URL = (
    "https://raw.githubusercontent.com/"
    "Bursuchok/Story-Reader/refs/heads/main/"
)

PUBLISHED_URL_PREFIX = (
    RAW_BASE_URL + quote("Published Stories", safe="/") + "/"
)

REQUIRED_FIELDS = [
    "title",
    "author",
    "genre",
    "description",
    "detailedDescription",
    "theme",
    "ageRating",
    "ratingDescription",
]


def make_url(path):
    relative_path = path.relative_to(ROOT).as_posix()
    return RAW_BASE_URL + quote(relative_path, safe="/")


def read_source(path):
    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines(keepends=True)

    if sum(line.strip() == METADATA_MARKER for line in lines) != 1:
        raise ValueError(
            f"{path.name}: маркер STORY-METADATA має бути рівно один."
        )

    if sum(line.strip() == CONTENT_MARKER for line in lines) != 1:
        raise ValueError(
            f"{path.name}: маркер STORY-CONTENT має бути рівно один."
        )

    metadata_line = next(
        i for i, line in enumerate(lines)
        if line.strip() == METADATA_MARKER
    )

    content_line = next(
        i for i, line in enumerate(lines)
        if line.strip() == CONTENT_MARKER
    )

    if content_line <= metadata_line:
        raise ValueError(
            f"{path.name}: маркери розташовані в неправильному порядку."
        )

    metadata_text = "".join(
        lines[metadata_line + 1:content_line]
    ).strip()

    content_lines = lines[content_line + 1:]

    if content_lines and not content_lines[0].strip():
        content_lines = content_lines[1:]

    content = "".join(content_lines)

    if not content.strip():
        raise ValueError(f"{path.name}: текст історії порожній.")

    try:
        metadata = json.loads(metadata_text)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"{path.name}: помилка JSON у метаданих: {error}"
        ) from error

    if not isinstance(metadata, dict):
        raise ValueError(
            f"{path.name}: метадані повинні бути JSON-об'єктом."
        )

    for field in REQUIRED_FIELDS:
        value = metadata.get(field)

        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                f"{path.name}: відсутнє або порожнє обов'язкове поле: {field}"
            )

    if "contentWarnings" not in metadata:
        raise ValueError(
            f"{path.name}: відсутнє обов'язкове поле: contentWarnings"
        )

    warnings = metadata["contentWarnings"]

    if not isinstance(warnings, list):
        raise ValueError(
            f"{path.name}: contentWarnings має бути списком."
        )

    if not all(
        isinstance(item, str) and item.strip()
        for item in warnings
    ):
        raise ValueError(
            f"{path.name}: кожне попередження має бути непорожнім текстом."
        )

    opening_tag = "<<storytype>>"
    closing_tag = "<</storytype>>"

    if content.count(opening_tag) != 1:
        raise ValueError(
            f"{path.name}: тег <<storytype>> має бути рівно один."
        )

    if content.count(closing_tag) != 1:
        raise ValueError(
            f"{path.name}: тег <</storytype>> має бути рівно один."
        )

    opening_position = content.find(opening_tag)
    closing_position = content.find(closing_tag)

    if closing_position <= opening_position:
        raise ValueError(
            f"{path.name}: теги storytype розташовані в неправильному порядку."
        )

    story_body = content[
        opening_position + len(opening_tag):closing_position
    ]

    if not story_body.strip():
        raise ValueError(
            f"{path.name}: між тегами storytype немає тексту."
        )

    return metadata, content


def main():
    if not CATALOG.exists():
        raise FileNotFoundError("Не знайдено catalog.json.")

    if not INBOX.exists():
        raise FileNotFoundError("Не знайдено папку New Stories.")

    try:
        catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Помилка JSON у catalog.json: {error}"
        ) from error

    if not isinstance(catalog, list):
        raise ValueError("catalog.json повинен містити JSON-масив.")

    source_files = sorted(INBOX.glob("*.txt"))

    # Спочатку перевіряємо всі вхідні файли.
    prepared = []
    seen_titles = set()

    for source in source_files:
        metadata, content = read_source(source)
        title_key = metadata["title"].strip().casefold()

        if title_key in seen_titles:
            raise ValueError(
                f"Дві історії в New Stories мають однакову назву: "
                f"{metadata['title']}"
            )

        seen_titles.add(title_key)
        prepared.append((source, metadata, content))

    # Готуємо нові записи каталогу та файли для публікації.
    new_catalog = list(catalog)
    updates = []

    for source, metadata, content in prepared:
        output_path = PUBLISHED / source.name
        url = make_url(output_path)

        record = dict(metadata)
        record["url"] = url

        matches = [
            i for i, item in enumerate(new_catalog)
            if isinstance(item, dict)
            and str(item.get("title", "")).strip().casefold()
            == metadata["title"].strip().casefold()
        ]

        if len(matches) > 1:
            raise ValueError(
                f"У catalog.json вже є кілька записів з назвою "
                f"{metadata['title']}. Спершу потрібно розібрати дублікати."
            )

        if matches:
            new_catalog[matches[0]] = record
            action = "Оновлено"
        else:
            new_catalog.append(record)
            action = "Додано"

        updates.append((output_path, content, action, metadata["title"]))

    # Записуємо підготовлені історії.
    PUBLISHED.mkdir(parents=True, exist_ok=True)

    for output_path, content, action, title in updates:
        output_path.write_text(content, encoding="utf-8")
        print(f"{action}: {title} → {output_path.relative_to(ROOT)}")

    # Збираємо URL усіх TXT-файлів, які реально залишилися опублікованими.
    published_urls = {
        make_url(path)
        for path in PUBLISHED.glob("*.txt")
        if path.is_file()
    }

    # Видаляємо з каталогу записи, чиї файли були видалені.
    cleaned_catalog = []
    removed_count = 0

    for item in new_catalog:
        if not isinstance(item, dict):
            cleaned_catalog.append(item)
            continue

        url = item.get("url", "")

        if (
            isinstance(url, str)
            and url.startswith(PUBLISHED_URL_PREFIX)
            and url not in published_urls
        ):
            print(
                f"Видалено з каталогу: "
                f"{item.get('title', 'Без назви')}"
            )
            removed_count += 1
        else:
            cleaned_catalog.append(item)

    # Зберігаємо каталог.
    CATALOG.write_text(
        json.dumps(cleaned_catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Видалено записів із каталогу: {removed_count}")
    print("Синхронізацію завершено успішно.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ПОМИЛКА: {error}", file=sys.stderr)
        sys.exit(1)
