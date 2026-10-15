from app.domain.category_guess import (
    CategorySource,
    ClickMapping,
    category_text,
    majority_mapping,
    resolve,
)
from app.domain.category_metrics import (
    acceptance,
    curve,
    histogram,
    macro_f1,
    pick_threshold,
    rejection_threshold,
    top_k_accuracy,
)


def test_ood_threshold_rejects_requested_share() -> None:
    unseen = [0.1, 0.2, 0.3, 0.4, 0.95]
    threshold = rejection_threshold(unseen, 0.8)
    assert threshold == 0.41
    assert acceptance(unseen, threshold) == 0.2
    assert rejection_threshold([], 0.8) == 0.0
    assert rejection_threshold([1.0, 1.0], 0.8) == 1.0
    assert histogram([0.05, 0.15, 0.99, 1.0], 10) == [1, 1, 0, 0, 0, 0, 0, 0, 0, 2]


def test_category_text_strips_html_and_normalizes() -> None:
    text = category_text("Ёлка ИСКУССТВЕННАЯ", "<p>Высота  <b>180</b> см</p>" + "x" * 500)
    assert text.startswith("елка искусственная высота 180 см")
    assert "<" not in text
    assert len(text) < 260


def test_majority_mapping_weights_by_clicks() -> None:
    mapping = majority_mapping([(10, 1, 5), (10, 2, 1), (10, 1, 4), (20, 3, 2)])
    assert mapping[10] == ClickMapping(1, 0.9)
    assert mapping[20] == ClickMapping(3, 1.0)


def test_resolve_prefers_catalog_then_clicks_then_classifier() -> None:
    clicks = ClickMapping(7, 0.95)
    ranked = [(9, 0.8), (8, 0.1)]
    by_catalog = resolve(1, 5, clicks, ranked, 0.5)
    assert by_catalog is not None and by_catalog.source is CategorySource.CATALOG
    by_clicks = resolve(1, None, clicks, ranked, 0.5)
    assert by_clicks is not None and by_clicks.category_id == 7
    by_model = resolve(1, None, None, ranked, 0.5)
    assert by_model is not None and by_model.source is CategorySource.CLASSIFIER
    assert resolve(1, None, None, ranked, 0.9) is None
    assert resolve(1, None, None, [], 0.0) is None


def test_ranking_metrics() -> None:
    truth = [1, 2, 3, 1]
    ranked = [[(1, 0.9), (2, 0.1)], [(3, 0.6), (2, 0.4)], [(3, 0.3), (1, 0.2)], [(1, 0.95)]]
    assert top_k_accuracy(truth, ranked, 1) == 0.75
    assert top_k_accuracy(truth, ranked, 2) == 1.0
    assert round(macro_f1(truth, [1, 3, 3, 1]), 4) == round((1 + 0 + 2 / 3) / 3, 4)
    points = curve(truth, ranked, [0.0, 0.5])
    assert points[1].coverage == 0.75 and round(points[1].precision, 4) == round(2 / 3, 4)
    assert pick_threshold(truth, ranked, 1.0) == 0.61
    assert pick_threshold(truth, [[(9, 0.99)]] * 4, 0.9) == 1.0
