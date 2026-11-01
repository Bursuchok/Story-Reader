
    
  

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

    # Кожна історія, яку публікуємо, отримує ідентичну копію в Saves.
    for published_path, content in planned_files.items():
        save_path = SAVES / published_path.name
        all_outputs[save_path] = content

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

        stats["saved"] = len(planned_files)

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
    print(f"Скопійовано в Saves: {stats['saved']}")
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
