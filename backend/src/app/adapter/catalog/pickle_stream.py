import struct
from array import array
from collections.abc import Buffer, Iterator
from typing import Final, cast

type Node = str | int | bool | None | dict[str, "Node"] | list["Node"]

_MARK: Final = object()
_CACHE_LIMIT: Final = 2_000_000


class UnsupportedPickle(ValueError):
    pass


def stream_list_items(data: Buffer, keys: frozenset[str]) -> Iterator[tuple[str, Node]]:
    view = memoryview(data)
    size = len(view)
    unpack_q = struct.Struct("<Q").unpack_from
    unpack_i = struct.Struct("<I").unpack_from
    unpack_h = struct.Struct("<H").unpack_from
    unpack_l = struct.Struct("<i").unpack_from
    stack: list[object] = []
    memo_off = array("q")
    memo_len = array("q")
    memo_scalar: dict[int, object] = {}
    cache: dict[int, str] = {}
    last_str: object = None
    last_off = -1
    last_len = 0
    pos = 0

    def text(off: int, length: int) -> str:
        return bytes(view[off : off + length]).decode("utf-8", "surrogatepass")

    def pop_mark() -> list[object]:
        items: list[object] = []
        while True:
            item = stack.pop()
            if item is _MARK:
                items.reverse()
                return items
            items.append(item)

    while pos < size:
        op = view[pos]
        pos += 1
        if op == 0x8C:
            length = view[pos]
            pos += 1
            last_off, last_len = pos, length
            last_str = text(pos, length)
            stack.append(last_str)
            pos += length
        elif op == 0x94:
            top = stack[-1]
            if top is last_str and isinstance(top, str):
                memo_off.append(last_off)
                memo_len.append(last_len)
            else:
                memo_off.append(-1)
                memo_len.append(0)
                if not isinstance(top, (dict, list)):
                    memo_scalar[len(memo_off) - 1] = top
        elif op in (0x68, 0x6A):
            if op == 0x68:
                index = view[pos]
                pos += 1
            else:
                index = unpack_i(view, pos)[0]
                pos += 4
            cached = cache.get(index)
            if cached is None:
                off = memo_off[index]
                if off < 0:
                    if index not in memo_scalar:
                        raise UnsupportedPickle(f"shared container reference at {pos}")
                    stack.append(memo_scalar[index])
                    continue
                cached = text(off, memo_len[index])
                if len(cache) >= _CACHE_LIMIT:
                    cache.clear()
                cache[index] = cached
            stack.append(cached)
        elif op == 0x28:
            stack.append(_MARK)
        elif op == 0x7D:
            stack.append({})
        elif op == 0x5D:
            stack.append([])
        elif op == 0x75:
            items = pop_mark()
            target = stack[-1]
            assert isinstance(target, dict)
            for i in range(0, len(items), 2):
                target[items[i]] = items[i + 1]
        elif op == 0x73:
            value = stack.pop()
            key = stack.pop()
            target = stack[-1]
            assert isinstance(target, dict)
            target[key] = value
        elif op in (0x65, 0x61):
            items = pop_mark() if op == 0x65 else [stack.pop()]
            owner = stack[-2] if len(stack) >= 2 else None
            if isinstance(owner, str) and owner in keys:
                for item in items:
                    yield owner, cast(Node, item)
            else:
                target = stack[-1]
                assert isinstance(target, list)
                target.extend(items)
        elif op == 0x58:
            length = unpack_i(view, pos)[0]
            pos += 4
            last_off, last_len = pos, length
            last_str = text(pos, length)
            stack.append(last_str)
            pos += length
        elif op == 0x8D:
            length = unpack_q(view, pos)[0]
            pos += 8
            last_off, last_len = pos, length
            last_str = text(pos, length)
            stack.append(last_str)
            pos += length
        elif op == 0x95:
            pos += 8
        elif op == 0x80:
            pos += 1
        elif op == 0x4E:
            stack.append(None)
        elif op == 0x88:
            stack.append(True)
        elif op == 0x89:
            stack.append(False)
        elif op == 0x4B:
            stack.append(view[pos])
            pos += 1
        elif op == 0x4D:
            stack.append(unpack_h(view, pos)[0])
            pos += 2
        elif op == 0x4A:
            stack.append(unpack_l(view, pos)[0])
            pos += 4
        elif op == 0x2E:
            return
        else:
            raise UnsupportedPickle(f"opcode {op:#04x} at {pos - 1}")
