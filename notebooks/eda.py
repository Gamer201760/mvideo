# ---
# jupyter:
#   jupytext:
#     formats: py:percent,ipynb
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# # Разведочный анализ данных: карточки, клики, каталог
#
# Данные — архив организаторов `dataset.zip` (SHA-256 в README), распакованный в
# `data/raw/`. Три файла:
#
# | Файл | Что внутри |
# |---|---|
# | `sku_desc.parquet` | Текст карточки: `sku_id`, `title`, `description` |
# | `query_clicks.parquet` | Клики из поиска: SKU, текст запроса, позиция, категория, цена |
# | `skus.pkl` | Выгрузка YML-каталога: категории и офферы с параметрами, в том числе `*_search` |
#
# Вопросы, на которые отвечает ноутбук: насколько полны и чисты текстовые поля; как распределён
# трафик по товарам и категориям; насколько велик длинный хвост; сколько характеристик уже лежит в
# описании в виде «ключ: значение»; как часто одно значение записано по-разному.
#
# Запуск: `uvx --with pandas --with pyarrow --with matplotlib --with ipykernel --with nbconvert
# jupytext --to ipynb --execute notebooks/eda.py`.

# %%
import re
from collections import Counter
from pathlib import Path

from IPython.display import display

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

ROOT = Path.cwd() if (Path.cwd() / "data").exists() else Path.cwd().parent
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
FIG = ROOT / "docs" / "images" / "eda"
FIG.mkdir(parents=True, exist_ok=True)
pd.set_option("display.max_colwidth", 120)
plt.rcParams.update({"figure.dpi": 110, "axes.spines.top": False, "axes.spines.right": False})


def save(fig, name):
    fig.tight_layout()
    fig.savefig(FIG / f"{name}.png", bbox_inches="tight")


# %% [markdown]
# ## 1. Обзор файлов

# %%
overview = []
for name in ["sku_desc.parquet", "query_clicks.parquet"]:
    meta = pq.ParquetFile(RAW / name).metadata
    overview.append({"файл": name, "строк": meta.num_rows, "колонок": meta.num_columns,
                     "МБ на диске": round((RAW / name).stat().st_size / 2**20, 1)})
overview.append({"файл": "skus.pkl", "строк": None, "колонок": None,
                 "МБ на диске": round((RAW / "skus.pkl").stat().st_size / 2**20, 1)})
pd.DataFrame(overview)

# %% [markdown]
# ## 2. Карточки: `sku_desc.parquet`

# %%
desc_file = pq.ParquetFile(RAW / "sku_desc.parquet")
n_desc = desc_file.metadata.num_rows
flags = {
    "title пустой или null": ("title", None),
    "description пустой или null": ("description", None),
    "description короче 50 символов": ("description", None),
    "в description есть блок «Характеристики:»": ("description", r"Характеристики:"),
    "в description есть строки «• ключ: значение»": ("description", r"•\s*[^:\n]{2,60}:\s*\S"),
    "в description есть HTML-теги": ("description", r"<\s*/?\s*(br|p|li|ul|b|div)\b"),
    "title заканчивается на « -» (пустая модель)": ("title", r"\s-\s*$"),
    "уценённый товар": ("title", r"(?i)^уцен"),
}
counts = Counter()
title_lens, body_lens = [], []
rng = np.random.default_rng(42)
sample_body = []
SAMPLE_RATE = 200_000 / n_desc


def count_true(mask):
    return pc.sum(pc.cast(pc.fill_null(mask, False), pa.int64())).as_py() or 0


for batch in desc_file.iter_batches(columns=["title", "description"], batch_size=100_000):
    title, body = batch.column(0), batch.column(1)
    tl = pc.fill_null(pc.utf8_length(title), 0)
    bl = pc.fill_null(pc.utf8_length(body), 0)
    title_lens.append(tl.to_numpy(zero_copy_only=False))
    body_lens.append(bl.to_numpy(zero_copy_only=False))
    counts["title пустой или null"] += count_true(pc.equal(tl, 0))
    counts["description пустой или null"] += count_true(pc.equal(bl, 0))
    counts["description короче 50 символов"] += count_true(pc.less(bl, 50))
    for name, (col, rx) in flags.items():
        if rx:
            counts[name] += count_true(pc.match_substring_regex(title if col == "title" else body, rx))
    take = np.flatnonzero(rng.random(len(body)) < SAMPLE_RATE)
    sample_body.extend(body.take(pa.array(take)).to_pylist())
    del title, body, batch

title_len, body_len = np.concatenate(title_lens), np.concatenate(body_lens)
desc_ids = pc.unique(pq.read_table(RAW / "sku_desc.parquet", columns=["sku_id"])["sku_id"])
print(f"Карточек: {n_desc:,}; дублей sku_id: {n_desc - len(desc_ids):,}")
quality = pd.DataFrame([{"признак": k, "% карточек": round(counts[k] / n_desc * 100, 2)} for k in flags])
quality

# %% [markdown]
# **Вывод.** Пропуски и мусор в тексте — первое, что видит пайплайн; доля блока «Характеристики:»
# определяет, сколько атрибутов закроет простой парсер «ключ: значение», и поэтому метрики считаются
# в двух режимах: с этим блоком и с вырезанным.

# %%
fig, axes = plt.subplots(1, 2, figsize=(11, 3.6))
for ax, arr, label in [(axes[0], title_len, "title"), (axes[1], body_len, "description")]:
    ax.hist(np.log10(arr + 1), bins=60, color="#3b6ea5")
    ax.set_title(f"Длина {label}, символов (log10)")
    ax.set_xlabel("log10(длина + 1)")
    ax.set_ylabel("карточек")
    q = np.percentile(arr, [50, 90, 99])
    ax.text(0.98, 0.95, f"p50={q[0]:.0f}\np90={q[1]:.0f}\np99={q[2]:.0f}", transform=ax.transAxes,
            ha="right", va="top", fontsize=9)
save(fig, "text_length")

# %% [markdown]
# ### Какие ключи встречаются в строках «ключ: значение»
#
# Случайная выборка ~200 тысяч описаний. Ключи — кандидаты в атрибуты, а разнобой в их записи
# показывает, сколько нормализации нужно уже на уровне названий атрибутов.

# %%
kv = re.compile(r"(?:^|\n)[ \t]*[•\-–]?[ \t]*([А-ЯЁA-Z][^:\n]{1,50}?)[ \t]*:[ \t]*([^\n]{1,80})")
keys, pairs = Counter(), Counter()
for text in sample_body:
    if not text:
        continue
    for k, v in kv.findall(text):
        k = k.strip().lower()
        keys[k] += 1
        pairs[(k, v.strip().lower())] += 1
top_keys = pd.DataFrame(keys.most_common(30), columns=["ключ", "карточек в выборке"])
top_keys

# %%
fig, ax = plt.subplots(figsize=(8, 6))
tk = top_keys.iloc[::-1]
ax.barh(tk["ключ"], tk["карточек в выборке"], color="#3b6ea5")
ax.set_title("Топ-30 ключей «ключ: значение» в описаниях (выборка 200 тыс.)")
ax.set_xlabel("карточек")
save(fig, "top_description_keys")

# %% [markdown]
# ### Одно значение — много записей
#
# Значения ключа «цвет» в той же выборке: сколько разных строк описывают несколько базовых цветов.

# %%
colors = Counter()
for (k, v), c in pairs.items():
    if k.startswith("цвет"):
        colors[v] += c
base = ["черн", "бел", "красн", "син", "сер", "зел"]
variants = {b: sorted([(v, c) for v, c in colors.items() if b in v], key=lambda x: -x[1]) for b in base}
pd.DataFrame([{"базовый цвет": b, "разных записей": len(vs),
               "примеры": ", ".join(v for v, _ in vs[:8])} for b, vs in variants.items()])

# %% [markdown]
# **Вывод.** Даже внутри одного ключа значения записаны десятками способов — справочник канонических
# значений с алиасами обязателен до любой модели.

# %%
del sample_body, title_lens, body_lens

# %% [markdown]
# ## 3. Клики: `query_clicks.parquet`

# %%
qc_file = pq.ParquetFile(RAW / "query_clicks.parquet")
cols = qc_file.schema_arrow.names
Q, NAME, BRAND = "toValidUTF8(query_text)", "toValidUTF8(sku_name)", "toValidUTF8(sku_brand_name)"
qc_parts, seo_ids = [], set()
for batch in qc_file.iter_batches(columns=["sku_id", "sku_subject_id", "sku_seo_id", "sku_position"],
                                  batch_size=2_000_000):
    qc_parts.append(pa.table({
        "sku_id": pc.cast(batch.column(0), pa.int64()),
        "sku_subject_id": pc.cast(batch.column(1), pa.int32()),
        "sku_position": pc.cast(batch.column(3), pa.int32()),
    }))
    seo_ids.update(pc.unique(batch.column(2)).to_pylist())
qc = pa.concat_tables(qc_parts)
del qc_parts
n_clicks = qc.num_rows
sku_clicks = qc.group_by("sku_id").aggregate([("sku_id", "count")]).rename_columns(["sku_id", "clicks"])
cat_clicks = qc.group_by("sku_subject_id").aggregate([("sku_id", "count"), ("sku_id", "count_distinct")])
cat_clicks = cat_clicks.rename_columns(["subject_id", "clicks", "skus"])
print(f"Кликов: {n_clicks:,}; уникальных SKU: {sku_clicks.num_rows:,}; "
      f"категорий (sku_subject_id): {cat_clicks.num_rows:,}; "
      f"seo-категорий: {len(seo_ids):,}")

# %%
empty = Counter()
for batch in qc_file.iter_batches(columns=[NAME, BRAND, Q], batch_size=2_000_000):
    for i, col in enumerate([NAME, BRAND, Q]):
        empty[col] += count_true(pc.equal(pc.fill_null(pc.utf8_length(batch.column(i)), 0), 0))
empty = {k: round(v / n_clicks * 100, 2) for k, v in empty.items()}
pd.DataFrame([{"колонка": k, "% пустых": v} for k, v in empty.items()])

# %% [markdown]
# ### Концентрация трафика
#
# Кривая показывает, какая доля SKU собирает какую долю кликов. Чем круче кривая, тем сильнее
# взвешивание по трафику расходится с простым средним по карточкам.

# %%
c = np.sort(sku_clicks["clicks"].to_numpy())[::-1]
cum = np.cumsum(c) / c.sum()
x = np.arange(1, len(c) + 1) / len(c)
top1, top10 = cum[int(len(c) * 0.01) - 1], cum[int(len(c) * 0.10) - 1]
fig, ax = plt.subplots(figsize=(6, 4))
ax.plot(x * 100, cum * 100, color="#3b6ea5")
ax.set_xlabel("% SKU, отсортированных по кликам")
ax.set_ylabel("% кликов")
ax.set_title(f"Топ-1% SKU — {top1:.0%} кликов, топ-10% — {top10:.0%}")
ax.grid(alpha=0.3)
save(fig, "traffic_concentration")
print(f"Медиана кликов на SKU: {np.median(c):.0f}; SKU с одним кликом: {(c == 1).mean():.1%}")

# %%
cc = cat_clicks.to_pandas().sort_values("clicks", ascending=False).reset_index(drop=True)
fig, ax = plt.subplots(figsize=(7, 4))
ax.loglog(np.arange(1, len(cc) + 1), cc["clicks"], color="#3b6ea5")
ax.set_xlabel("ранг категории")
ax.set_ylabel("кликов")
ax.set_title("Длинный хвост категорий по трафику")
ax.grid(alpha=0.3, which="both")
save(fig, "category_long_tail")
head_share = cc["clicks"].head(50).sum() / cc["clicks"].sum()
print(f"Топ-50 категорий — {head_share:.0%} кликов; категорий с < 100 кликами: {(cc['clicks'] < 100).sum():,}")

# %%
pos = qc["sku_position"].to_numpy()
fig, ax = plt.subplots(figsize=(6, 3.4))
ax.hist(np.clip(pos, 0, 60), bins=61, color="#3b6ea5")
ax.set_title("Позиция кликнутого SKU в выдаче (обрезано на 60)")
ax.set_xlabel("позиция")
ax.set_ylabel("кликов")
save(fig, "click_position")
del qc, pos

# %% [markdown]
# ### Какие атрибуты ищут: значения характеристик в текстах запросов
#
# Если покупатель пишет в запросе «256 гб» или «черный», атрибут работает на поиск. Доля запросов с
# упоминанием атрибута — основа веса атрибута при взвешивании метрик по трафику.

# %%
patterns = {
    "объём памяти": r"\b\d{2,4}\s?(гб|gb|тб|tb)\b",
    "диагональ": r"\b\d{2}([.,]\d)?\s?(\"|дюйм|''|”)",
    "цвет": r"\b(черн|бел|красн|син|сер|зел|золот|розов|фиолет|голуб|бежев|black|white)\w*",
    "мощность": r"\b\d{2,5}\s?(вт|w|квт)\b",
    "ёмкость батареи": r"\b\d{3,5}\s?(мач|mah)\b",
    "объём, л": r"\b\d+([.,]\d)?\s?(л|литр)\w*\b",
    "процессор": r"\b(i[3579]|ryzen|core|m[1-4]\b|snapdragon|apple m)",
    "оперативная память": r"\b(озу|ram|оперативн)",
}
hits, n_q = Counter(), 0
for batch in qc_file.iter_batches(columns=[Q], batch_size=2_000_000):
    col = pc.utf8_lower(batch.column(0))
    n_q += len(col)
    for name, rx in patterns.items():
        hits[name] += pc.sum(pc.cast(pc.fill_null(pc.match_substring_regex(col, rx), False), pa.int64())).as_py()
attr_demand = pd.DataFrame([{"атрибут": k, "% кликов из запросов с ним": round(v / n_q * 100, 2)}
                            for k, v in hits.most_common()])
attr_demand

# %%
fig, ax = plt.subplots(figsize=(7, 3.6))
ad = attr_demand.iloc[::-1]
ax.barh(ad["атрибут"], ad["% кликов из запросов с ним"], color="#3b6ea5")
ax.set_xlabel("% кликов")
ax.set_title("Атрибуты, которые покупатели пишут в поисковых запросах")
save(fig, "attribute_demand")

# %%
parts = []
for batch in qc_file.iter_batches(columns=[Q], batch_size=2_000_000):
    lowered = pa.table({"q": pc.utf8_trim_whitespace(pc.utf8_lower(batch.column(0)))})
    parts.append(lowered.group_by("q").aggregate([("q", "count")]))
queries = pa.concat_tables(parts).group_by("q").aggregate([("q_count", "sum")])
del parts
print(f"Уникальных запросов: {queries.num_rows:,}")
top_idx = pc.select_k_unstable(queries, k=25, sort_keys=[("q_count_sum", "descending")])
queries.take(top_idx).to_pandas().set_axis(["запрос", "кликов"], axis=1)

# %% [markdown]
# ## 4. Связка файлов
#
# Сколько карточек с текстом имеют клики. Пересечение с каталогом `skus.pkl` (а значит, с эталоном
# `*_search`) считается в подготовке данных и подтягивается из `data/processed/`, если она уже
# прогнана.

# %%
click_ids = sku_clicks["sku_id"]
in_clicks = pc.is_in(desc_ids, value_set=click_ids)
n_both = pc.sum(pc.cast(in_clicks, pa.int64())).as_py()
print(f"Карточек с текстом: {len(desc_ids):,}; из них с кликами: {n_both:,} ({n_both / len(desc_ids):.1%})")
print(f"SKU с кликами, но без текста: {sku_clicks.num_rows - n_both:,}")

# %% [markdown]
# ## 5. Каталог и эталон
#
# Разделы ниже читают таблицы из `data/processed/`, которые строит подготовка данных: покрытие
# атрибутов эталоном, распределение значений `*_search`, разнобой «продавец ↔ эталон», обязательные
# атрибуты по категориям.

# %%
offers = pq.read_table(PROCESSED / "cards.parquet", columns=["sku_id", "category_id", "seller"],
                       filters=[("in_catalog", "=", True)])
categories = pq.read_table(PROCESSED / "categories.parquet").to_pandas().set_index("category_id")
splits = pq.read_table(PROCESSED / "splits.parquet")
gold_file = pq.ParquetFile(PROCESSED / "gold.parquet")
offer_ids = offers["sku_id"]
with_text = pc.is_in(offer_ids, value_set=desc_ids)
print(f"Офферов в каталоге: {len(offer_ids):,}; с текстом в sku_desc: {pc.sum(pc.cast(with_text, pa.int64())).as_py():,}")
print(f"Строк эталона (SKU × атрибут): {gold_file.metadata.num_rows:,}")
pd.DataFrame(pc.value_counts(splits["split"]).to_pylist()).set_axis(["сплит", "SKU"], axis=1)

# %% [markdown]
# ### Покрытие атрибутов эталоном
#
# Сколько атрибутов `*_search` у одного SKU и какие атрибуты заполнены чаще всего. Атрибуты из длинного
# хвоста встречаются у единиц товаров — на них нельзя обучить отдельную модель, только правила,
# справочники и LLM.

# %%
attr_parts, per_sku_parts = [], []
for batch in gold_file.iter_batches(columns=["sku_id", "attribute"], batch_size=2_000_000):
    t = pa.table({"sku_id": batch.column(0), "attribute": batch.column(1)})
    attr_parts.append(t.group_by("attribute").aggregate([("sku_id", "count")]))
    per_sku_parts.append(t.group_by("sku_id").aggregate([("attribute", "count")]))
attr_cov = (pa.concat_tables(attr_parts).group_by("attribute").aggregate([("sku_id_count", "sum")])
            .to_pandas().set_axis(["атрибут", "SKU"], axis=1).sort_values("SKU", ascending=False))
per_sku = (pa.concat_tables(per_sku_parts).group_by("sku_id").aggregate([("attribute_count", "sum")])
           .column(1).to_numpy())
del attr_parts, per_sku_parts
n_offers = len(offer_ids)
attr_cov["% офферов"] = (attr_cov["SKU"] / n_offers * 100).round(2)
print(f"Разных атрибутов: {len(attr_cov):,}; медиана атрибутов на SKU: {np.median(per_sku):.0f}; "
      f"атрибутов, заполненных у < 100 SKU: {(attr_cov['SKU'] < 100).sum():,}")
attr_cov.head(20).reset_index(drop=True)

# %%
fig, axes = plt.subplots(1, 2, figsize=(11, 3.6))
axes[0].hist(np.clip(per_sku, 0, 80), bins=40, color="#3b6ea5")
axes[0].set_title("Атрибутов эталона на один SKU (обрезано на 80)")
axes[0].set_xlabel("атрибутов")
axes[0].set_ylabel("SKU")
axes[1].loglog(np.arange(1, len(attr_cov) + 1), attr_cov["SKU"].to_numpy(), color="#3b6ea5")
axes[1].set_title("Длинный хвост атрибутов: SKU с атрибутом по рангу")
axes[1].set_xlabel("ранг атрибута")
axes[1].set_ylabel("SKU")
axes[1].grid(alpha=0.3, which="both")
save(fig, "gold_attribute_coverage")

# %% [markdown]
# ### Обязательные атрибуты: смартфоны и ноутбуки
#
# Подготовка данных выбирает обязательные атрибуты категории: бренд, модель и самые заполненные
# атрибуты, ранжированные по кликам. `weight` — вес атрибута во взвешенных по трафику метриках.

# %%
required = pq.read_table(PROCESSED / "required_attributes.parquet").to_pandas()
LEAVES = {761: "Смартфоны", 987: "Ноутбуки"}
for cid, label in LEAVES.items():
    r = required[required["category_id"] == cid].sort_values("rank")
    print(f"{label} ({categories.loc[cid, 'path']}): {len(r)} обязательных атрибутов")
    display(r[["attribute", "card_coverage", "click_coverage", "query_share", "weight"]].reset_index(drop=True))
print(f"Категорий с обязательными атрибутами: {required['category_id'].nunique():,}; "
      f"в среднем атрибутов на категорию: {required.groupby('category_id').size().mean():.1f}")

# %% [markdown]
# ### Есть ли значение эталона в тексте карточки
#
# Главный вопрос для каскада с цитатами: если значения нет в тексте, извлечь его честно нельзя.
# Выборка 20 тысяч SKU из train с текстом; для каждого обязательного атрибута проверяем, встречается
# ли значение эталона в `title` + `description` дословно (без учёта регистра и «ё»). Это верхняя
# граница recall для извлечения без выдумывания. Второй режим — то же, но с вырезанным блоком
# «Характеристики:».

# %%
def norm(s):
    return re.sub(r"\s+", " ", (s or "").lower().replace("ё", "е"))


spec_block = re.compile(r"Характеристики:.*", re.S)
train_ids = pc.filter(splits["sku_id"], pc.equal(splits["split"], "train"))
train_text = pc.filter(train_ids, pc.is_in(train_ids, value_set=desc_ids)).to_numpy()
sample_ids = np.random.default_rng(7).choice(train_text, size=min(20_000, len(train_text)), replace=False)
sample_set = pa.array(sample_ids)
texts = pq.read_table(RAW / "sku_desc.parquet", filters=[("sku_id", "in", sample_set)]).to_pandas()
texts["full"] = (texts["title"].fillna("") + " \n " + texts["description"].fillna("")).map(norm)
texts["no_block"] = (texts["title"].fillna("") + " \n "
                     + texts["description"].fillna("").map(lambda d: spec_block.sub("", d))).map(norm)
texts = texts.set_index("sku_id")
gold_s = pq.read_table(PROCESSED / "gold.parquet", filters=[("sku_id", "in", sample_set)]).to_pandas()
cat_of = offers.to_pandas().set_index("sku_id")["category_id"]
gold_s["category_id"] = gold_s["sku_id"].map(cat_of)
req_pairs = set(zip(required["category_id"], required["attribute"]))
gold_s = gold_s[[(c, a) in req_pairs for c, a in zip(gold_s["category_id"], gold_s["attribute"])]]
gold_s = gold_s[gold_s["sku_id"].isin(texts.index)]
vals = gold_s["value"].map(norm)
gold_s["в тексте"] = [v in texts.at[s, "full"] for v, s in zip(vals, gold_s["sku_id"])]
gold_s["в тексте без блока"] = [v in texts.at[s, "no_block"] for v, s in zip(vals, gold_s["sku_id"])]
grounding = (gold_s.groupby("attribute")[["в тексте", "в тексте без блока"]].mean().mul(100).round(1)
             .join(gold_s.groupby("attribute").size().rename("пар")).sort_values("пар", ascending=False))
print(f"Пар SKU × обязательный атрибут: {len(gold_s):,}; значение найдено в тексте: "
      f"{gold_s['в тексте'].mean():.1%}; без блока «Характеристики:»: {gold_s['в тексте без блока'].mean():.1%}")
grounding.head(20)

# %%
top = grounding.head(15).iloc[::-1]
fig, ax = plt.subplots(figsize=(8, 5.5))
y = np.arange(len(top))
ax.barh(y + 0.2, top["в тексте"], height=0.4, color="#3b6ea5", label="весь текст")
ax.barh(y - 0.2, top["в тексте без блока"], height=0.4, color="#a5c3e0", label="без блока «Характеристики:»")
ax.set_yticks(y, top.index)
ax.set_xlabel("% пар, где значение эталона дословно есть в тексте")
ax.set_title("Значение эталона в тексте карточки (выборка 20 тыс. SKU)")
ax.legend(loc="lower right", fontsize=8)
save(fig, "gold_value_in_text")

# %% [markdown]
# ### Продавец ↔ эталон: сколько нормализации нужно
#
# Для атрибутов, которые есть и у продавца, и в эталоне под тем же именем, — доля точных совпадений
# значения. Несовпадение — работа для справочника алиасов и правил единиц.

# %%
seller = pq.read_table(PROCESSED / "cards.parquet", columns=["sku_id", "seller_params"],
                       filters=[("sku_id", "in", sample_set)]).to_pandas()
rows = [(r.sku_id, p["name"], p["value"]) for r in seller.itertuples() for p in (r.seller_params if r.seller_params is not None else [])]
seller_long = pd.DataFrame(rows, columns=["sku_id", "attribute", "seller_value"])
gold_all = pq.read_table(PROCESSED / "gold.parquet", filters=[("sku_id", "in", sample_set)]).to_pandas()
pairs_sg = seller_long.merge(gold_all, on=["sku_id", "attribute"])
pairs_sg["совпадает"] = pairs_sg["seller_value"].map(norm) == pairs_sg["value"].map(norm)
mismatch = (pairs_sg.groupby("attribute")["совпадает"].agg(["mean", "size"])
            .rename(columns={"mean": "доля совпадений", "size": "пар"}).sort_values("пар", ascending=False))
mismatch["доля совпадений"] = (mismatch["доля совпадений"] * 100).round(1)
print(f"Пар продавец ↔ эталон: {len(pairs_sg):,}; совпадают дословно: {pairs_sg['совпадает'].mean():.1%}")
display(mismatch.head(15))
pairs_sg.loc[~pairs_sg["совпадает"], ["attribute", "seller_value", "value", "unit"]].head(15)

# %% [markdown]
# ## 6. Выводы для пайплайна
#
# Числа — с прогона 2026-10-14 на полном архиве; ячейки выше пересчитывают их при каждом запуске.
#
# 1. **Текст есть всегда, но грязный.** Пустых `title`/`description` нет, зато почти половина описаний
#    содержит HTML, а у четверти `title` пустая модель («Брелок UNIMALL -»). Препроцессинг: снять HTML,
#    не доверять `title` как источнику модели.
# 2. **Блок «Характеристики:» есть почти только у карточек вне каталога.** Среди всех описаний он
#    встречается у ~29%, но среди 241 тыс. карточек с эталоном — лишь у ~8 тыс.: каталожные описания
#    написаны свободным текстом. Парсер «ключ: значение» полезен для 1,2 млн карточек без эталона
#    (файл предсказаний), а качество на эталоне держится на словарях, единицах и модели.
# 3. **Нормализация — не косметика.** Только у ключа «цвет» в выборке больше сотни разных записей
#    одного базового цвета («черный», «чёрный», «черный матовый», «черное», «black»). Справочник
#    канонических значений с алиасами нужен до любой модели.
# 4. **Трафик сильно сконцентрирован.** Топ-1% SKU собирает 38% кликов, топ-10% — 81%; топ-50
#    категорий — 70% кликов, а у 2 341 из 4 103 категорий меньше 100 кликов. Метрики, взвешенные по
#    трафику, и средние по карточкам будут сильно расходиться — показываем оба.
# 5. **Атрибуты редко пишут в запросе.** Запросы в основном категорийные («стиральная машинка»,
#    «холодильники»); явное упоминание памяти, процессора, диагонали — доли процента кликов. Вес
#    атрибута по одним запросам будет шумным; основной вес — клики категории, упоминания в запросах —
#    поправка.
# 6. **Связка файлов.** Клики есть у 13% карточек с текстом; эталон (`*_search`) — у 241 тыс. карточек
#    с текстом (пересечение `skus.pkl` и `sku_desc`), из них ~103 тыс. ещё и с кликами. Этого хватает
#    на обучение, валидацию и отложенные категории.
# 7. **Не всё из эталона есть в тексте.** Для обязательных атрибутов значение эталона дословно
#    встречается в `title` + `description` в ~58% пар: бренд и модель — 96–99%, высота и ширина —
#    ~70%, цвет — ~26%, вес — ~3%. Часть расхождения — формат (запятая вместо точки, единицы), часть —
#    значения, которых в тексте действительно нет. Каскад с обязательной цитатой честно ограничен этим
#    потолком; recall считаем и относительно него, а недостающее берём из атрибутов продавца.
# 8. **Атрибуты продавца — это фасеты-диапазоны, а эталон — точные значения.** Дословно совпадает
#    ~62% пар; у числовых атрибутов совпадений нет вовсе: продавец пишет «2 - 2.99 кг», эталон — «2.3 кг».
#    Диапазон продавца — ограничение для кандидатов из текста, а не готовый ответ.
# 9. **Список обязательных по трафику расходится с ТЗ.** Для смартфонов по кликам выходят бренд,
#    модель, серия, процессор, диагональ, память; ёмкости батареи и цвета нет. Для ноутбуков нет RAM,
#    накопителя и диагонали. ТЗ называет эти поля явно (раздел 6), поэтому для двух примерных категорий
#    список ТЗ добавляется к списку по трафику.
