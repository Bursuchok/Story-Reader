
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


class PublishError(Exception):
    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(message)


def error(code, message):
    raise PublishError(code, message)


def make_url(path):
    relative_path = path.relative_to(ROOT).as_posix()
    return RAW_BASE_URL + quote(relative_path, safe="/")


def read_source(path):
    # E101: файл неможливо прочитати.
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        error("E101", f"{path.name} — файл має неправильне кодування. Потрібен UTF-8.")
    except OSError as exc:
        error("E101", f"{path.name} — не вдалося прочитати файл: {exc}")

    lines = text.splitlines(keepends=True)

    metadata_count = sum(
        line.strip() == METADATA_MARKER for line in lines
    )
    content_count = sum(
        line.strip() == CONTENT_MARKER for line in lines
    )

    # E102–E105: перевірка маркерів.
    if metadata_count == 0:
        error("E102", f"{path.name} — відсутній маркер STORY-METADATA.")

    if metadata_count > 1:
        error("E103", f"{path.name} — маркер STORY-METADATA повторюється.")

    if content_count == 0:
        error("E104", f"{path.name} — відсутній маркер STORY-CONTENT.")

    if content_count > 1:
        error("E105", f"{path.name} — маркер STORY-CONTENT повторюється.")

    metadata_line = next(
        i for i, line in enumerate(lines)
        if line.strip() == METADATA_MARKER
    )

    content_line = next(
        i for i, line in enumerate(lines)
        if line.strip() == CONTENT_MARKER
    )

    # E106: неправильний порядок маркерів.
    if content_line <= metadata_line:
        error(
            "E106",
            f"{path.name} — STORY-METADATA має бути перед STORY-CONTENT."
        )

    metadata_text = "".join(
        lines[metadata_line + 1:content_line]
    ).strip()

    content_lines = lines[content_line + 1:]

    if content_lines and not content_lines[0].strip():
        content_lines = content_lines[1:]

    content = "".join(content_lines)

    # E107: порожня історія.
    if not content.strip():
        error("E107", f"{path.name} — текст історії відсутній або порожній.")

    # E108: неправильний JSON.
    try:
        metadata = json.loads(metadata_text)
    except json.JSONDecodeError as exc:
        error(
            "E108",
            f"{path.name} — помилка JSON у метаданих: "
            f"рядок {exc.lineno}, стовпець {exc.colno}: {exc.msg}."
        )

    # E109: кореневий елемент не є об'єктом.
    if not isinstance(metadata, dict):
        error(
            "E109",
            f"{path.name} — метадані повинні бути JSON-об'єктом у фігурних дужках."
        )

    # E110: обов'язкове поле відсутнє.
    # E111: обов'язкове поле має неправильний тип або порожнє.
    for field in REQUIRED_FIELDS:
        if field not in metadata:
            error(
                "E110",
                f'{path.name} — відсутнє обов’язкове поле "{field}".'
            )

        value = metadata[field]

        if not isinstance(value, str) or not value.strip():
            error(
                "E111",
                f'{path.name} — поле "{field}" має бути непорожнім текстом.'
            )

    # E112: contentWarnings відсутнє.
    if "contentWarnings" not in metadata:
        error(
            "E112",
            f'{path.name} — відсутнє обов’язкове поле "contentWarnings".'
        )

    warnings = metadata["contentWarnings"]

    # E113: contentWarnings не є списком.
    if not isinstance(warnings, list):
        error(
            "E113",
            f'{path.name} — "contentWarnings" має бути списком [].'
        )

    # E114: неправильний елемент списку попереджень.
    if not all(
        isinstance(item, str) and item.strip()
        for item in warnings
    ):
        error(
            "E114",
            f"{path.name} — кожне попередження має бути непорожнім текстом."
        )

    # Перевірка тегів storytype.
    opening_tag = "<<storytype>>"
    closing_tag = "<</storytype>>"

    opening_count = content.count(opening_tag)
    closing_count = content.count(closing_tag)

    # E115–E118: перевірка тегів.
    if opening_count == 0:
        error("E115", f"{path.name} — відсутній тег <<storytype>>.")

    if opening_count > 1:
        error("E116", f"{path.name} — тег <<storytype>> повторюється.")

    if closing_count == 0:
        error("E117", f"{path.name} — відсутній тег <</storytype>>.")

    if closing_count > 1:
        error("E118", f"{path.name} — тег <</storytype>> повторюється.")

    opening_position = content.find(opening_tag)
    closing_position = content.find(closing_tag)

    # E119: неправильний порядок тегів.
    if closing_position <= opening_position:
        error(
            "E119",
            f"{path.name} — <<storytype>> має стояти перед <</storytype>>."
        )

    story_body = content[
        opening_position + len(opening_tag):closing_position
    ]

    # E120: порожній текст між тегами.
    if not story_body.strip():
        error(
            "E120",
            f"{path.name} — між тегами storytype немає тексту."
        )

    return metadata, content


def main():
    # E001: немає каталогу.
    if not CATALOG.exists():
        error("E001", "Не знайдено файл catalog.json.")

    # E002: немає папки для нових історій.
    if not INBOX.exists():
        error("E002", "Не знайдено папку New Stories.")

    # E003: каталог неможливо прочитати.
    try:
        catalog_text = CATALOG.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        error("E003", f"Не вдалося прочитати catalog.json: {exc}")

    # E004: каталог містить неправильний JSON.
    try:
        catalog = json.loads(catalog_text)
    except json.JSONDecodeError as exc:
        error(
            "E004",
            f"Помилка JSON у catalog.json: "
            f"рядок {exc.lineno}, стовпець {exc.colno}: {exc.msg}."
        )

    # E005: каталог не є масивом.
    if not isinstance(catalog, list):
        error("E005", "catalog.json повинен містити JSON-масив [].")

    source_files = sorted(INBOX.glob("*.txt"))

    if not source_files:
        print("У New Stories немає TXT-файлів.")

    # Спочатку перевіряємо всі вхідні файли.
    prepared = []
    seen_titles = set()

    for source in source_files:
        metadata, content = read_source(source)
        title_key = metadata["title"].strip().casefold()

        # E121: дубль назви серед нових історій.
        if title_key in seen_titles:
            error(
                "E121",
                f'Дві історії в New Stories мають однакову назву: '
                f'"{metadata["title"]}".'
            )

        seen_titles.add(title_key)
        prepared.append((source, metadata, content))

    # Готуємо записи каталогу та файли для публікації.
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

        # E122: кілька записів з однаковою назвою в каталозі.
        if len(matches) > 1:
            error(
                "E122",
                f'У catalog.json знайдено кілька записів з назвою '
                f'"{metadata["title"]}". Потрібно виправити дублікати.'
            )

        if matches:
            new_catalog[matches[0]] = record
            action = "Оновлено"
        else:
            new_catalog.append(record)
            action = "Додано"

        updates.append(
            (output_path, content, action, metadata["title"])
        )

    # Записуємо підготовлені історії.
    try:
        PUBLISHED.mkdir(parents=True, exist_ok=True)

        for output_path, content, action, title in updates:
            output_path.write_text(content, encoding="utf-8")
            print(
                f"{action}: {title} → "
                f"{output_path.relative_to(ROOT)}"
            )

    except OSError as exc:
        error("E006", f"Не вдалося записати опубліковану історію: {exc}")

    # Збираємо URL усіх TXT-файлів, які залишилися опублікованими.
    published_urls = {
        make_url(path)
        for path in PUBLISHED.glob("*.txt")
        if path.is_file()
    }

    # Видаляємо записи, чиї опубліковані файли видалені.
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
    try:
        CATALOG.write_text(
            json.dumps(cleaned_catalog, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        error("E007", f"Не вдалося зберегти catalog.json: {exc}")

    print(f"Видалено записів із каталогу: {removed_count}")
    print("Синхронізацію завершено успішно.")


if __name__ == "__main__":
    try:
        main()
    except PublishError as exc:
        print(
            f"[{exc.code}] {exc.message}",
            file=sys.stderr
        )
        sys.exit(1)
    except Exception as exc:
        print(
            f"[E999] Непередбачена помилка: {exc}",
            file=sys.stderr
        )
        sys.exit(1)
