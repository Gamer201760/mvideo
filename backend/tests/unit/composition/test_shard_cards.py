from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from app.run_shard_cards import main


def test_shards_partition_cards_and_link_other_tables(tmp_path: Path) -> None:
    data = tmp_path / "processed"
    data.mkdir()
    pq.write_table(pa.table({"sku_id": pa.array(range(1, 11), pa.int64()),
                             "title": [f"t{i}" for i in range(1, 11)]}), data / "cards.parquet")
    pq.write_table(pa.table({"sku_id": pa.array([1], pa.int64())}), data / "splits.parquet")
    out = tmp_path / "shards"
    main(["--data", str(data), "--out", str(out), "--shards", "3"])
    ids = [sorted(pq.read_table(out / str(i) / "cards.parquet")["sku_id"].to_pylist())
           for i in range(3)]
    assert ids == [[3, 6, 9], [1, 4, 7, 10], [2, 5, 8]]
    assert (out / "0" / "splits.parquet").is_symlink()
