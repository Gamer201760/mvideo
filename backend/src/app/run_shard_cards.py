import argparse
import os
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

CARDS = "cards.parquet"
BATCH = 50_000


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Split cards into shards for parallel runs")
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--shards", type=int, default=5)
    args = parser.parse_args(argv)
    data: Path = args.data.resolve()
    out: Path = args.out
    count: int = args.shards
    for shard in range(count):
        folder = out / str(shard)
        folder.mkdir(parents=True, exist_ok=True)
        for item in data.iterdir():
            link = folder / item.name
            if item.name == CARDS or not item.is_file():
                continue
            if link.is_symlink() or link.exists():
                link.unlink()
            os.symlink(item, link)
    source = pq.ParquetFile(data / CARDS)
    writers = [pq.ParquetWriter(out / str(i) / CARDS, source.schema_arrow) for i in range(count)]
    for batch in source.iter_batches(batch_size=BATCH):
        table = pa.Table.from_batches([batch])
        remainder = pc.subtract(table["sku_id"],
                                pc.multiply(pc.divide(table["sku_id"], count), count))
        for shard, writer in enumerate(writers):
            writer.write_table(table.filter(pc.equal(remainder, shard)))
    for writer in writers:
        writer.close()
    print(" ".join(str(pq.ParquetFile(out / str(i) / CARDS).metadata.num_rows)
                   for i in range(count)))


if __name__ == "__main__":
    main()
