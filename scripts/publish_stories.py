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

REQUIRED_FIELDS = [
    "title",
    "author",
    "genre",
    "description",
    "detailedDescription",
    "theme",
    "ageRating",
]


def read_source(path):
    text = path.read_text(encoding="utf-8-sig")
    lines = text.splitlines(keepends=True)

    metadata_line = next(
        (i for i, line in enumerate(lines)
         if line.strip() == METADATA_MARKER),
        None,
    )
    content_line = next(
        (i for i, line in enumerate(lines)
         if line.strip() == CONTENT_MARKER),
        None,
    )

    if metadata_line is None or content_line is None:
        raise ValueError(
            "Не знайдено маркери STORY-METADATA або STORY-CONTENT."
        )

    if content_line <= metadata_line:
        raise ValueError("Маркери розташовані в неправильному порядку.")

    metadata_text = "".join(lines[metadata_line + 1:content_line]).strip()
    content_lines = lines[content_line + 1:]

    # Прибираємо один порожній рядок після маркера, якщо він є.
    if content_lines and not content_lines[0].strip():
        content_lines = content_lines[1:]

    content = "".join(content_lines)

    if not content.strip():
        raise ValueError("Текст історії порожній.")

    metadata = json.loads(metadata_text)

    if not isinstance(metadata, dict):
        raise ValueError("Метадані повинні бути JSON-об'єктом.")

    for field in REQUIRED_FIELDS:
        if not isinstance(metadata.get(field), str) or not metadata[field].strip():
            raise ValueError(f"Відсутнє обов'язкове поле: {field}")

    warnings = metadata.get("contentWarnings", [])
    if not isinstance(warnings, list) or not all(
        isinstance(item, str) for item in warnings
    ):
        raise ValueError("contentWarnings має бути списком текстових значень.")

    return metadata, content


def main():
    if not CATALOG.exists():
        raise FileNotFoundError("Не знайдено catalog.json.")

    if not INBOX.exists():
        raise FileNotFoundError("Не знайдено папку New Stories.")

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))

    if not isinstance(catalog, list):
        raise ValueError("catalog.json повинен містити JSON-масив.")

    source_files = sorted(INBOX.glob("*.txt"))

    if not source_files:
        print("У New Stories немає TXT-файлів.")
        return

    # Спочатку перевіряємо всі джерела. Якщо є помилка — нічого не публікуємо.
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

    PUBLISHED.mkdir(parents=True, exist_ok=True)

    for source, metadata, content in prepared:
        output_path = PUBLISHED / source.name

        relative_path = output_path.relative_to(ROOT).as_posix()
        encoded_path = quote(relative_path, safe="/")
        url = (
            "https://raw.githubusercontent.com/"
            "Bursuchok/Story-Reader/refs/heads/main/"
            + encoded_path
        )

        record = dict(metadata)
        record["url"] = url

        # Знаходимо історію за назвою: оновлюємо її, якщо вона вже є.
        matches = [
            i for i, item in enumerate(catalog)
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
            catalog[matches[0]] = record
            action = "Оновлено"
        else:
            catalog.append(record)
            action = "Додано"

        output_path.write_text(content, encoding="utf-8")
        print(f"{action}: {metadata['title']} → {relative_path}")

    CATALOG.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print("Публікацію завершено успішно.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"ПОМИЛКА: {error}", file=sys.stderr)
        sys.exit(1)
