from app.adapter.category.classifier import TfidfLinearClassifier, analyze


def test_analyze_mixes_words_pairs_and_char_grams() -> None:
    grams = analyze("ноутбук asus")
    assert "w ноутбук" in grams
    assert "b ноутбук asus" in grams
    assert " но" in grams and "sus " in grams


def test_classifier_ranks_known_category_first() -> None:
    texts = ["смартфон samsung galaxy", "смартфон xiaomi redmi", "ноутбук lenovo ideapad",
             "ноутбук asus vivobook"] * 5
    labels = [761, 761, 987, 987] * 5
    model = TfidfLinearClassifier(jobs=1, epochs=20)
    model.fit(texts, labels)
    ranked = model.rank(["смартфон honor", "ноутбук hp"], 2)
    assert [r[0][0] for r in ranked] == [761, 987]
    assert all(0.0 <= p <= 1.0 for r in ranked for _, p in r)
