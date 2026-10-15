from collections.abc import Mapping

KIND_NAMES = {"description": "(a) только описание", "page": "(b) HTML-страница с шумом",
              "paragraph": "(c) все поля одним абзацем"}


def render_text_report(report: Mapping[str, object], index: Mapping[str, object]) -> str:
    kinds = _map(report.get("kinds"))
    structured = _map(report.get("structured"))
    config = _map(report.get("config"))
    cost = _map(report.get("cost"))
    lines = [
        "# Извлечение из сплошного текста",
        "",
        f"Выборка: {config.get('test_cards')} карточек test из категорий стенда и "
        f"{config.get('new_category_cards')} карточек new_category, сид {config.get('seed')}; "
        f"входов обработано: {report.get('inputs')}"
        + (" (остановлено по бюджету)." if report.get("stopped_by_budget") else "."),
        f"Поиск по каталогу: {report.get('search')}; название: {report.get('title_mode')}.",
        "",
        "## Категория",
        "",
        ("| Вид входа | top-1 | top-3 | macro-F1 | покрытие при пороге | точность при пороге "
        "| new_category отклонено |"),
        "|---|---|---|---|---|---|---|",
    ]
    for kind, raw in kinds.items():
        c = _map(_map(raw).get("category"))
        lines.append(f"| {KIND_NAMES.get(kind, kind)} | {_pct(c.get('top1'))} | "
                     f"{_pct(c.get('top3'))} | {_pct(c.get('macro_f1'))} | "
                     f"{_pct(c.get('coverage'))} | {_pct(c.get('precision'))} | "
                     f"{_pct(c.get('new_category_rejected'))} |")
    lines += ["", "## Название", "", ("| Вид входа | точно | нечётко (≥ 0,8) | средняя близость "
              "| из LLM |"), "|---|---|---|---|---|"]
    for kind, raw in kinds.items():
        t = _map(_map(raw).get("title"))
        lines.append(f"| {KIND_NAMES.get(kind, kind)} | {_pct(t.get('exact'))} | "
                     f"{_pct(t.get('fuzzy'))} | {_pct(t.get('mean_ratio'))} | "
                     f"{_pct(t.get('from_llm'))} |")
    lines += ["", "## Обязательные атрибуты (эталон `*_search`, карточки test)", "",
              "| Вход | P | R | F1 | macro-F1 | заполнено | с цитатой | секунд на вход (p95) |",
              "|---|---|---|---|---|---|---|---|"]
    for kind, raw in kinds.items():
        k = _map(raw)
        a = _map(k.get("attributes"))
        s = _map(k.get("seconds"))
        lines.append(f"| {KIND_NAMES.get(kind, kind)} | {_pct(a.get('precision'))} | "
                     f"{_pct(a.get('recall'))} | {_pct(a.get('f1'))} | "
                     f"{_pct(k.get('attributes_macro_f1'))} | {_pct(a.get('coverage_after'))} | "
                     f"{_pct(k.get('quoted_share'))} | {s.get('mean')} ({s.get('p95')}) |")
    lines.append(f"| Структурированная карточка, верхняя граница | "
                 f"{_pct(structured.get('precision'))} | {_pct(structured.get('recall'))} | "
                 f"{_pct(structured.get('f1'))} | {_pct(report.get('structured_macro_f1'))} | "
                 f"{_pct(structured.get('coverage_after'))} | — | — |")
    lines += ["", "## Стоимость", "",
              (f"Оплачено в этом прогоне: {cost.get('spent_rub')} ₽ за {cost.get('paid_calls')} "
               "вызовов; ответы из кэша не оплачиваются. Цена входа считается по оплаченным "
               "вызовам (на вход — один вызов LLM и один вызов эмбеддингов): "
               f"{cost.get('per_input_rub')} ₽, ≈ {cost.get('per_million_rub')} ₽ на 1 млн "
               "входов."), "", "## Калибровка категории на val", "",
              "| Поиск | входов | top-1 | top-3 | порог | покрытие | точность |",
              "|---|---|---|---|---|---|---|"]
    for kind, raw in index.items():
        r = _map(raw)
        lines.append(f"| {kind} | {r.get('val_inputs')} | {_pct(r.get('top1'))} | "
                     f"{_pct(r.get('top3'))} | {r.get('threshold')} | {_pct(r.get('coverage'))} "
                     f"| {_pct(r.get('precision'))} |")
    return "\n".join(lines) + "\n"


def _map(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _pct(value: object) -> str:
    return f"{float(value) * 100:.1f}" if isinstance(value, int | float) else "—"
