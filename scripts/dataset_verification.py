import hashlib
import zlib
from collections.abc import Iterator
from pathlib import Path

from dataset_manifest import DatasetFile, DatasetManifest, load_manifest
from dataset_package_io import BLOCK_BYTES


def verified_blocks(package: Path, item: DatasetFile) -> Iterator[bytes]:
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
    digest = hashlib.sha256()
    total = 0
    try:
        for part in item["parts"]:
            part_hash, part_size = hashlib.sha256(), 0
            path = package / part["name"]
            if path.is_symlink():
                raise ValueError("Dataset part was replaced with a symlink")
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(BLOCK_BYTES), b""):
                    part_hash.update(block)
                    part_size += len(block)
                    if part_size > part["size"]:
                        raise ValueError("Dataset part changed during verification")
                    pending = block
                    while True:
                        restored = decoder.decompress(pending, BLOCK_BYTES)
                        pending = decoder.unconsumed_tail
                        if decoder.unused_data:
                            raise ValueError("Unexpected trailing compressed data")
                        if restored:
                            total += len(restored)
                            if total > item["size"]:
                                raise ValueError("Restored dataset exceeds its declared size")
                            digest.update(restored)
                            yield restored
                        if not pending and len(restored) < BLOCK_BYTES:
                            break
            if part_size != part["size"] or part_hash.hexdigest() != part["sha256"]:
                raise ValueError(f"Dataset part checksum mismatch: {part['name']}")
        if not decoder.eof or total != item["size"] or digest.hexdigest() != item["sha256"]:
            raise ValueError(f"Dataset file checksum or gzip mismatch: {item['name']}")
    except zlib.error:
        raise ValueError(f"Corrupted gzip stream: {item['name']}") from None


def verify(package: Path) -> DatasetManifest:
    manifest = load_manifest(package)
    for item in manifest["files"]:
        for _ in verified_blocks(package, item):
            pass
    return manifest
