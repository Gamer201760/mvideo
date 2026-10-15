import hashlib
import random
from collections.abc import Collection, Mapping
from enum import StrEnum


class Split(StrEnum):
    TRAIN = "train"
    VAL = "val"
    TEST = "test"
    NEW_CATEGORY = "new_category"


def split_of(sku_id: int, seed: int, val_share: float, test_share: float) -> Split:
    digest = hashlib.sha1(f"{seed}:{sku_id}".encode()).digest()
    fraction = int.from_bytes(digest[:8], "big") / 2**64
    if fraction < test_share:
        return Split.TEST
    if fraction < test_share + val_share:
        return Split.VAL
    return Split.TRAIN


def pick_new_categories(
    sizes: Mapping[int, int],
    seed: int,
    count: int,
    min_size: int,
    max_size: int,
    exclude: Collection[int] = (),
) -> list[int]:
    eligible = sorted(
        category
        for category, size in sizes.items()
        if min_size <= size <= max_size and category not in exclude
    )
    if len(eligible) <= count:
        return eligible
    return sorted(random.Random(seed).sample(eligible, count))
