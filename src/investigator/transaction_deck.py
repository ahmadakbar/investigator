import csv
import hashlib
from array import array
from pathlib import Path
from typing import Iterator, Self, Sequence, overload

from pydantic import ValidationError

from investigator.schemas import Outcome, Record, Transaction


class RowError(Exception):
    def __init__(self, message: str, index: int, raw: bytes, values: list[str] | None = None):
        super().__init__(message)
        self.index = index
        self.raw = raw          # exact bytes consumed from the file
        self.values = values    # parsed fields, if parsing got that far

class TransactionDeck(Sequence[Record]):
    """Random-access view of a transactions CSV.

    Construction makes one pass: SHA-256 digest plus the byte offset of each
    record. Rows are parsed and validated only when accessed.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._file = self.path.open("rb")
        self._offsets = array("q")     # 8 bytes per record
        self._line_nos = array("q")
        self.digest, self.fieldnames = self._index()

    def _index(self) -> tuple[str, list[str]]:
        sha = hashlib.sha256()
        pos = line_no = 0

        def lines() -> Iterator[str]:
            nonlocal pos, line_no
            for raw in self._file:
                sha.update(raw)
                pos += len(raw)
                line_no += 1
                yield raw.decode("utf-8")

        reader = csv.reader(lines())
        fieldnames = next(reader, [])
        while True:
            start, start_line = pos, line_no + 1
            values = next(reader, None)
            if values is None:
                break
            if values:                 # skip blank lines, as DictReader does
                self._offsets.append(start)
                self._line_nos.append(start_line)
        return sha.hexdigest(), fieldnames

    def __len__(self) -> int:
        return len(self._offsets)

    def _normalize(self, i: int) -> int:
        try:
            return range(len(self))[i]
        except IndexError:
            raise IndexError(
                f"record index {i} out of range ({len(self)} records)"
            ) from None

    @overload
    def __getitem__(self, i: int) -> Record: ...

    @overload
    def __getitem__(self, i: slice) -> list[Record]: ...

    def __getitem__(self, i: int | slice) -> Record | list[Record]:
        if isinstance(i, slice):
            return [self._load(j) for j in range(len(self))[i]]
        return self._load(self._normalize(i))

    def _read_row(self, i: int) -> tuple[dict[str, str], bytes]:
        self._file.seek(self._offsets[i])
        raw_lines: list[bytes] = []

        def lines():
            for raw in self._file:
                raw_lines.append(raw)           # saved before decoding
                yield raw.decode("utf-8")

        values = None
        try:
            values = next(csv.reader(lines()))
            row = dict(zip(self.fieldnames, values, strict=True))
        except (StopIteration, UnicodeDecodeError, ValueError, csv.Error) as e:
            raise RowError(
                f"row {i}: {e!r}", index=i, raw=b"".join(raw_lines), values=values
            ) from e
        return row, b"".join(raw_lines)

    def _load(self, i: int) -> Record:
        num, line_no = i + 1, self._line_nos[i]
        row: dict[str, str] = {}
        raw: bytes=b""
        try:
            row, raw  = self._read_row(i)
            tx = Transaction(**row)
        except ValidationError as e:
            return Record(num, line_no, Outcome.INVALID, row, str(raw, "utf-8"), error=e)
        except RowError as e:
            return Record(num, line_no, Outcome.ERROR, row, str(e.raw, "utf-8")  , error=e)
        except Exception as e:
            return Record(num, line_no, Outcome.ERROR, row, str(raw, "utf-8"), error=e)
        return Record(num, line_no, Outcome.OK, row, str(raw, "utf-8"), transaction=tx)

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def load_transactions(path: str | Path) -> TransactionDeck:
    return TransactionDeck(path)