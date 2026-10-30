
import argparse
import json
import os
import sys
import tempfile

from pathlib import Path
from urllib.parse import quote


# ============================================================
# НАЛАШТУВАННЯ
# ============================================================

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

# Обов'язкові поля нової історії.
REQUIRED_FIELDS = [
    "title",
    "author",
    "genre",
    "description",
    "detailedDescription",
    "theme",
    "ageRating",
]

# Необов'язкові поля.
OPTIONAL_CONTENT_FIELDS = [
    "contentWarnings",
    "ratingDescription",
]

# Межі довжини не блокують публікацію.
FIELD_LENGTH_LIMITS = {
    "title": 100,
    "description": 300,
    "detailedDescription": 1500,
    "ratingDescription": 1000,
}


# ============================================================
# ПОМИЛКИ ТА СТАТИСТИКА
# ============================================================

class PublishError(Exception):
    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(message)


def error(code, message):
    raise PublishError(code, message)


stats = {
    "added": 0,
    "updated": 0,
    "unchanged": 0,
    "removed": 0,
    "orphans": 0,
    "warnings": 0,
}


def warning(message):
    stats["warnings"] += 1
    print(f"[УВАГА] {message}")


# ============================================================
# ДОПОМІЖНІ ФУНКЦІЇ
# ============================================================

def make_url(path):
    relative_path = path.relative_to(ROOT).as_posix()
    return RAW_BASE_URL + quote(relative_path, safe="/")


def normalize(value):
    return value.strip().casefold()


def duplicate_json_keys(pairs):
    result = {}

    for key, value in pairs:
        if key in result:
            raise ValueError(f"Повторюється JSON-ключ: {key}")

        result[key] = value

    return result


def load_json(text, filename):
    try:
        return json.loads(
            text,
            object_pairs_hook=duplicate_json_keys
        )
    except json.JSONDecodeError as exc:
        error(
            "E004",
            f"{filename}: рядок {exc.lineno}, "
            f"стовпець {exc.colno}: {exc.msg}."
        )
    except ValueError as exc:
        error("E008", f"{filename}: {exc}")


def is_published_url(url):
    return (
        isinstance(url, str)
        and url.startswith(PUBLISHED_URL_PREFIX)
    )


def published_filename_from_url(url):
    if not is_published_url(url):
        return None

    relative = url[len(PUBLISHED_URL_PREFIX):]

    # Не дозволяємо URL виходити за межі Published Stories.
    if not relative or "/" in relative or "\\" in relative:
        return None

    filename = relative

    if not filename.lower().endswith(".txt"):
        return None

    return filename


# ============================================================
# ПЕРЕВІРКА МЕТАДАНИХ НОВОЇ ІСТОРІЇ
# ============================================================

def validate_metadata(metadata, filename):
    if not isinstance(metadata, dict):
        error(
            "E109",
            f"{filename} — метадані повинні бути JSON-об'єктом."
        )

    # --------------------------------------------------------
    # 1. Обов'язкові поля
    # --------------------------------------------------------

    for field in REQUIRED_FIELDS:
        if field not in metadata:
            error(
                "E110",
                f'{filename} — відсутнє поле "{field}".'
            )

        value = metadata[field]

        if not isinstance(value, str) or not value.strip():
            error(
                "E111",
                f'{filename} — поле "{field}" має бути непорожнім текстом.'
            )

    # --------------------------------------------------------
    # 2. Необов'язкові попередження про зміст
    # --------------------------------------------------------

    if "contentWarnings" not in metadata:
        warning(
            f'{filename} — відсутнє поле "contentWarnings". '
            "Публікація продовжується без позначок про чутливий зміст."
        )

    else:
        warnings_list = metadata["contentWarnings"]

        if not isinstance(warnings_list, list):
            warning(
                f'{filename} — "contentWarnings" має бути списком. '
                "Значення не перевірено."
            )

        elif not warnings_list:
            warning(
                f'{filename} — список "contentWarnings" порожній.'
            )

        elif not all(
            isinstance(item, str) and item.strip()
            for item in warnings_list
        ):
            warning(
                f'{filename} — "contentWarnings" містить '
                "некоректні елементи."
            )

    # --------------------------------------------------------
    # 3. Необов'язковий опис вікового рейтингу
    # --------------------------------------------------------

    if "ratingDescription" not in metadata:
        warning(
            f'{filename} — відсутнє поле "ratingDescription". '
            "Пояснення вікового рейтингу не додано."
        )

    else:
        rating_description = metadata["ratingDescription"]

        if (
            not isinstance(rating_description, str)
            or not rating_description.strip()
        ):
            warning(
                f'{filename} — поле "ratingDescription" порожнє '
                "або має неправильний формат."
            )

    # --------------------------------------------------------
    # 4. Рекомендовані межі довжини
    # --------------------------------------------------------

    for field, limit in FIELD_LENGTH_LIMITS.items():
        value = metadata.get(field)

        if isinstance(value, str) and len(value) > limit:
            warning(
                f'{filename} — поле "{field}" має '
                f'{len(value)} символів. '
                f"Рекомендована межа: {limit}."
            )

    return metadata


# ============================================================
# ЧИТАННЯ ТА ПЕРЕВІРКА НОВИХ ІСТОРІЙ
# ============================================================

def read_source(path):
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        error(
            "E101",
            f"{path.name} — неправильне кодування. Потрібен UTF-8."
        )
    except OSError as exc:
        error("E101", f"{path.name} — не вдалося прочитати файл: {exc}")

    lines = text.splitlines(keepends=True)

    metadata_count = sum(
        line.strip() == METADATA_MARKER for line in lines
    )

    content_count = sum(
        line.strip() == CONTENT_MARKER for line in lines
    )

    if metadata_count == 0:
        error("E102", f"{path.name} — відсутній STORY-METADATA.")

    if metadata_count > 1:
        error("E103", f"{path.name} — STORY-METADATA повторюється.")

    if content_count == 0:
        error("E104", f"{path.name} — відсутній STORY-CONTENT.")

    if content_count > 1:
        error("E105", f"{path.name} — STORY-CONTENT повторюється.")

    metadata_line = next(
        i for i, line in enumerate(lines)
        if line.strip() == METADATA_MARKER
    )

    content_line = next(
        i for i, line in enumerate(lines)
        if line.strip() == CONTENT_MARKER
    )

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

    if not content.strip():
        error("E107", f"{path.name} — текст історії порожній.")

    metadata = load_json(metadata_text, path.name)
    validate_metadata(metadata, path.name)

    opening_tag = "<<storytype>>"
    closing_tag = "<</storytype>>"

    opening_count = content.count(opening_tag)
    closing_count = content.count(closing_tag)

    if opening_count == 0:
        error("E115", f"{path.name} — відсутній <<storytype>>.")

    if opening_count > 1:
        error("E116", f"{path.name} — <<storytype>> повторюється.")

    if closing_count == 0:
        error("E117", f"{path.name} — відсутній <</storytype>>.")

    if closing_count > 1:
        error("E118", f"{path.name} — <</storytype>> повторюється.")

    opening_position = content.find(opening_tag)
    closing_position = content.find(closing_tag)

    if closing_position <= opening_position:
        error(
            "E119",
            f"{path.name} — теги storytype стоять у неправильному порядку."
        )

    story_body = content[
        opening_position + len(opening_tag):closing_position
    ]

    if not story_body.strip():
        error("E120", f"{path.name} — текст між тегами storytype порожній.")

    return metadata, content


# ============================================================
# ЧИТАННЯ КАТАЛОГУ
# ============================================================

def load_catalog():
    if not CATALOG.exists():
        error("E001", "Не знайдено catalog.json.")

    try:
        catalog_text = CATALOG.read_text(encoding="utf-8-sig")
    except OSError as exc:
        error("E003", f"Не вдалося прочитати catalog.json: {exc}")

    if not catalog_text.strip():
        print("Каталог порожній. Буде створено новий [].")
        return []

    catalog = load_json(catalog_text, "catalog.json")

    # Для роботи потрібен JSON-масив.
    if not isinstance(catalog, list):
        error("E005", "catalog.json повинен містити JSON-масив [].")

    # Жодних перевірок старих записів:
    # не перевіряємо поля, назви, URL, дублікати чи метадані.
    return catalog


# ============================================================
# ПЕРЕВІРКА ФАЙЛІВ
# ============================================================

def get_txt_files(folder):
    if not folder.exists():
        return []

    return sorted(
        path for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() == ".txt"
    )


def check_filename_collisions(files):
    seen = {}

    for path in files:
        key = path.name.casefold()

        if key in seen:
            error(
                "E012",
                f'Конфлікт назв файлів: "{seen[key].name}" '
                f'і "{path.name}".'
            )

        seen[key] = path


# ============================================================
# ОСНОВНА ЛОГІКА
# ============================================================

def main(dry_run=False):
    print("=" * 55)
    print("STORY READER — БІБЛІОТЕКАР")
    print("=" * 55)

    if not INBOX.exists():
        error("E002", "Не знайдено папку New Stories.")

    catalog = load_catalog()

    source_files = get_txt_files(INBOX)
    published_files = get_txt_files(PUBLISHED)

    check_filename_collisions(source_files)
    check_filename_collisions(published_files)

    print(f"\nФайлів у New Stories: {len(source_files)}")
    print(f"Опублікованих файлів: {len(published_files)}")
    print(f"Записів у каталозі: {len(catalog)}")

    # --------------------------------------------------------
    # 1. Перевірка всіх нових історій
    # --------------------------------------------------------

    prepared = []
    seen_titles = set()

    for source in source_files:
        metadata, content = read_source(source)

        title_key = normalize(metadata["title"])

        if title_key in seen_titles:
            error(
                "E121",
                f'У New Stories повторюється назва "{metadata["title"]}".'
            )

        seen_titles.add(title_key)

        prepared.append((source, metadata, content))

    # --------------------------------------------------------
    # 2. Підготовка нового каталогу
    # --------------------------------------------------------

    new_catalog = [
        dict(item) if isinstance(item, dict) else item
        for item in catalog
    ]

    planned_files = {}

    for source, metadata, content in prepared:
        output_path = PUBLISHED / source.name
        url = make_url(output_path)

        title_key = normalize(metadata["title"])

        # Шукаємо збіг лише серед записів-об'єктів.
        # Решту старих елементів каталогу не перевіряємо.
        matches = [
            i for i, item in enumerate(new_catalog)
            if (
                isinstance(item, dict)
                and isinstance(item.get("title"), str)
                and normalize(item["title"]) == title_key
            )
        ]

        # Якщо є кілька збігів, оновлюємо перший.
        # Інші старі записи не перевіряються і не блокують процес.
        if matches:
            index = matches[0]

            # Зберігаємо додаткові поля старого запису.
            record = dict(new_catalog[index])
            record.update(metadata)
            record["url"] = url

            if record == new_catalog[index]:
                stats["unchanged"] += 1
                action = "Без змін"
            else:
                stats["updated"] += 1
                action = "Оновлено"

            new_catalog[index] = record

        else:
            record = dict(metadata)
            record["url"] = url

            new_catalog.append(record)
            stats["added"] += 1
            action = "Додано"

        planned_files[output_path] = content

        print(f"[{action}] {metadata['title']}")

    # --------------------------------------------------------
    # 3. Пошук опублікованих файлів без запису в каталозі
    # --------------------------------------------------------

    catalog_urls = {
        item.get("url")
        for item in new_catalog
        if (
            isinstance(item, dict)
            and isinstance(item.get("url"), str)
        )
    }

    planned_names = {
        path.name.casefold()
        for path in planned_files
    }

    orphan_files = []

    for path in published_files:
        url = make_url(path)

        if (
            path.name.casefold() not in planned_names
            and url not in catalog_urls
        ):
            orphan_files.append(path)

    stats["orphans"] = len(orphan_files)

    for path in orphan_files:
        warning(
            f"Опублікований файл {path.name} не має запису в каталозі. "
            "Автоматично відновити метадані неможливо."
        )

    # --------------------------------------------------------
    # 4. Синхронізація видалених файлів
    # --------------------------------------------------------

    published_urls = {
        make_url(path)
        for path in published_files
    }

    published_urls.update(
        make_url(path)
        for path in planned_files
    )

    cleaned_catalog = []

    for item in new_catalog:
        # Необ'єктні елементи залишаємо без змін.
        if not isinstance(item, dict):
            cleaned_catalog.append(item)
            continue

        url = item.get("url", "")

        filename = published_filename_from_url(url)

        if (
            filename is not None
            and url not in published_urls
        ):
            print(
                f"[ВИДАЛЕНО З КАТАЛОГУ] "
                f"{item.get('title', 'Без назви')}"
            )
            stats["removed"] += 1
        else:
            cleaned_catalog.append(item)

    new_catalog = cleaned_catalog

    # --------------------------------------------------------
    # 5. ЗВІТ
    # --------------------------------------------------------

    print("\n" + "=" * 55)
    print("ЗВІТ ПЕРЕВІРКИ")
    print("=" * 55)

    print(f"Додано:                  {stats['added']}")
    print(f"Оновлено:                {stats['updated']}")
    print(f"Без змін:                {stats['unchanged']}")
    print(f"Видалено з каталогу:     {stats['removed']}")
    print(f"Загублених файлів:       {stats['orphans']}")
    print(f"Попереджень:             {stats['warnings']}")

    print(f"\nЗаписів у новому каталозі: {len(new_catalog)}")

    if dry_run:
        print("\nDRY-RUN: жодних файлів не змінено.")
        print("Перевірка завершена.")
        return

    # --------------------------------------------------------
    # 6. ПІДГОТОВКА ЗМІН
    # --------------------------------------------------------

    catalog_output = (
        json.dumps(
            new_catalog,
            ensure_ascii=False,
            indent=2
        ) + "\n"
    )

    all_outputs = dict(planned_files)
    all_outputs[CATALOG] = catalog_output

    # --------------------------------------------------------
    # 7. БЕЗПЕЧНИЙ ЗАПИС
    # --------------------------------------------------------

    temp_files = []

    try:
        for path, content in all_outputs.items():
            path.parent.mkdir(parents=True, exist_ok=True)

            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temp:
                temp.write(content)
                temp.flush()
                os.fsync(temp.fileno())
                temp_files.append((Path(temp.name), path))

        # Після успішної підготовки замінюємо файли.
        for temp_path, destination in temp_files:
            os.replace(temp_path, destination)

    except OSError as exc:
        for temp_path, _ in temp_files:
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except OSError:
                pass

        error("E006", f"Не вдалося записати файли: {exc}")

    # --------------------------------------------------------
    # 8. ЗАВЕРШЕННЯ
    # --------------------------------------------------------

    print("\n" + "=" * 55)
    print("ПУБЛІКАЦІЮ ЗАВЕРШЕНО")
    print("=" * 55)

    print(f"Додано:              {stats['added']}")
    print(f"Оновлено:            {stats['updated']}")
    print(f"Без змін:            {stats['unchanged']}")
    print(f"Видалено записів:    {stats['removed']}")
    print(f"Загублених файлів:   {stats['orphans']}")
    print(f"Попереджень:         {stats['warnings']}")

    print("\nБібліотека синхронізована успішно.")


# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Story Reader — автоматичний бібліотекар."
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Перевірити бібліотеку без внесення змін."
    )

    args = parser.parse_args()

    try:
        main(dry_run=args.dry_run)

    except PublishError as exc:
        print(
            f"\n[{exc.code}] {exc.message}",
            file=sys.stderr
        )
        sys.exit(1)

    except Exception as exc:
        print(
            f"\n[E999] Непередбачена помилка: {exc}",
            file=sys.stderr
        )
        sys.exit(1)
