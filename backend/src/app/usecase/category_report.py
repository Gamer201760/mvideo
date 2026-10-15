from collections.abc import Mapping

BIN_LABELS = [f"{i / 10:.1f}–{(i + 1) / 10:.1f}" for i in range(10)]


def render_markdown(report: Mapping[str, object]) -> str:
    test = _mapping(report.get("classifier_test"))
    selection = _mapping(report.get("threshold_selection"))
    clicks = _mapping(report.get("clicks"))
    coverage = _mapping(report.get("coverage"))
    lines = [
        "# Категории для карточек вне каталога",
        "",
        (f"Категорий с обязательными атрибутами: {report.get('required_categories')}; "
         f"обучающих карточек: {report.get('train_cards')}."),
        "",
        "## Выбор порога",
        "",
        (f"Порог {report.get('threshold')} = max(порог точности {report.get('target_precision')} "
         f"на val → {selection.get('by_val_precision')}; порог, отвергающий ≥ "
         f"{report.get('ood_reject_share')} карточек new_category → "
         f"{selection.get('by_new_category_rejection')})."),
        "",
        "| Набор | Карточек | Принято при пороге | Точность принятых |",
        "|---|---|---|---|",
        (f"| val (известные категории) | {selection.get('val_cards')} | "
         f"{_pct(selection.get('val_coverage'))} | {_pct(selection.get('val_precision'))} |"),
        (f"| new_category (неизвестные категории) | {selection.get('new_category_cards')} | "
         f"{_pct(_rest(selection.get('new_category_rejected')))} | — |"),
        (f"| вне каталога, без кликов | {coverage.get('outside_catalog_without_clicks')} | "
         f"{_pct(coverage.get('classifier_accepted_share'))} | не измерена |"),
        "",
        "### Распределение max-вероятности классификатора",
        "",
        "| Вероятность | val | new_category | вне каталога |",
        "|---|---|---|---|",
    ]
    columns = [_shares(selection.get("val_histogram")),
               _shares(selection.get("new_category_histogram")),
               _shares(coverage.get("outside_catalog_max_probability_histogram"))]
    for i, label in enumerate(BIN_LABELS):
        lines.append(f"| {label} | " + " | ".join(_pct(c[i]) if i < len(c) else "—"
                                                    for c in columns) + " |")
    lines += [
        "",
        "## Классификатор по названию (test, известные категории)",
        "",
        "| Карточек | Top-1 | Top-3 | Macro-F1 | Покрытие при пороге | Точность при пороге |",
        "|---|---|---|---|---|---|",
        (f"| {test.get('cards')} | {test.get('top1')} | {test.get('top3')} | "
         f"{test.get('macro_f1')} | {test.get('coverage_at_threshold')} | "
         f"{test.get('precision_at_threshold')} |"),
        "",
        "## Категория из кликов (test)",
        "",
        (f"Карточек test с кликами: {clicks.get('test_cards')}; сопоставлено: "
         f"{clicks.get('test_mapped')}; точность сопоставления: {clicks.get('test_accuracy')}; "
         f"`sku_seo_id` совпадает с категорией каталога напрямую: "
         f"{clicks.get('direct_id_match')}."),
        "",
        "## Итог по всем карточкам с текстом",
        "",
        (f"Карточек: {coverage.get('cards')}; с категорией: {coverage.get('with_category')} "
         f"({_pct(coverage.get('share_with_category'))}); по источникам: "
         f"{coverage.get('by_source')}."),
        "",
        "## Случайные карточки вне каталога для ручной проверки",
        "",
        "| Текст | Предсказанная категория | p | Принята |",
        "|---|---|---|---|",
    ]
    for sample in _points(coverage.get("samples")):
        text = str(sample.get("text", "")).replace("|", "/")
        lines.append(f"| {text} | {sample.get('category')} | {sample.get('probability')} | "
                     f"{'да' if sample.get('accepted') else 'нет'} |")
    lines.append("")
    return "\n".join(lines)


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _points(value: object) -> list[Mapping[str, object]]:
    return [p for p in value if isinstance(p, Mapping)] if isinstance(value, list) else []


def _shares(value: object) -> list[float]:
    counts = [v for v in value if isinstance(v, int)] if isinstance(value, list) else []
    total = sum(counts)
    return [c / total for c in counts] if total else []


def _rest(value: object) -> float | None:
    return 1 - value if isinstance(value, int | float) else None


def _pct(value: object) -> str:
    return f"{value * 100:.1f}%" if isinstance(value, int | float) else "—"
