# ByteJSON

> [!WARNING]
> **Experimental.** ByteJSON is a prototype, not a production-ready library. APIs, the on-disk index format, and performance characteristics may change without notice.

Random access to very large JSON files without loading the whole file into memory.

```python
from bytejson import open

db = open("reddit.json")
print(db["posts"][500]["title"])
```

```text
JSON file → binary index (byte offsets) → mmap → lazy reads → dict/list-like API
```

A hand-written scanner walks the file once and records where every value lives; its type, byte offset, length, and relationship to its parent; without materializing values into Python objects. The resulting metadata is written to a compact `.bjidx` index containing an mmap-backed node table, dictionary-encoded keys, and a CSR-style children index. Object lookups use indexed keys, while array lookups resolve directly by index without scanning.

After the index is built, `db["a"]["b"][3]` jumps directly to the relevant bytes and decodes only the requested value.

## Why ByteJSON?

Python's built-in `json.load()` is a great choice when you need most or all of a JSON document. For very large JSON files, however, loading the entire document can require substantial memory even when an application only needs a small number of values.

ByteJSON targets the opposite workload: large, mostly read-only JSON documents where applications perform a relatively small number of random lookups.

The trade-off is an index-building step and additional disk space for the `.bjidx` index.

## Setup

```bash
uv sync
uv run python examples/generate_sample.py
uv run python examples/demo.py
uv run python examples/benchmark.py
uv run pytest
```

## Performance

Measured with `examples/benchmark.py` using approximately 15,000 posts and 5,000 users (~8 MB JSON). Run the benchmark on your own data for representative numbers.

| Metric                                   | Result                         |
| ---------------------------------------- | ------------------------------ |
| Index size                               | ~123–128% of source JSON       |
| Warm open (existing index)               | ~1–5 ms                        |
| Random-access crossover vs `json.load()` | roughly 10,000–20,000+ lookups |
| Peak Python-heap memory (warm)           | single-digit MB                |

Below the crossover point, ByteJSON can benefit workloads that perform relatively few random lookups because it avoids materializing the entire document. As the number of lookups increases, the overhead of repeatedly resolving and decoding values eventually outweighs the benefit of lazy access, and a fully parsed Python object can become faster.

The crossover point is workload- and data-dependent. See `examples/benchmark.py` for the complete benchmark output and methodology.

> [!NOTE]
> The index can currently be larger than the source JSON. ByteJSON trades additional disk space for random-access capabilities and lower Python-heap usage.

## Example

```python
from bytejson import open

db = open("reddit.json")

posts = db["posts"]

post = posts[500]

title = posts[500]["title"]

print(title)
```

Objects and arrays behave like lightweight dictionary/list-like views rather than ordinary materialized Python objects.

## Project structure

```text
bytejson/
    __init__.py       public API: build_index, open, ByteJSONFile
    index.py          scanner: walks the file and locates every value
    storage.py        binary index: node table, key dictionary,
                      and CSR children index
    parser.py         decodes a located byte range into a Python value
    lazy.py           LazyObject / LazyArray dict/list-like views
    mmap_reader.py    mmap-backed random-access file reader
    utils.py          byte-class constants and file fingerprinting

examples/
    generate_sample.py
    demo.py
    benchmark.py

tests/
    pytest suite
```

## Scope

> [!NOTE]
> Read-only prototype; no writes, no mutation, and no stability guarantees on the `.bjidx` index format between versions.

Currently supported:

* Objects
* Arrays
* Strings
* Numbers
* Booleans
* `null`
* Random access through dictionary/list-like APIs

Currently out of scope:

* JSONPath queries
* Writes or mutation
* Compression
* Streaming index construction

## Known limitations

* **Index construction is currently single-threaded.** Building the index requires scanning the entire JSON document and is `O(document size)`. For cold opens, index construction is the dominant cost.

* **Deeply nested JSON.** The scanner recurses for nested structures. Extremely deep JSON documents, potentially thousands of levels, could hit Python's recursion limit.

* **File-change detection is partial.** ByteJSON currently samples the first and last 4 KiB of the JSON file along with its size. A modification in the middle of a file that preserves the original file size could therefore go undetected.

* **Warm-open memory is not zero.** Although ByteJSON avoids materializing the entire JSON document, the children index, key dictionary, and lookup cache remain in memory.

## Where this could go next

* **Native scanner**: A Cython or Rust implementation could provide the largest performance improvement, since the Python-level scanner currently dominates cold index construction time.

* **Parallel index construction**: Large files could potentially be indexed using multiple CPU cores.

* **Streaming index construction**: Support for building indexes without the current whole-file mmap-based approach would make ByteJSON more suitable for substantially larger files.

* **Smaller indexes**: Varint-encoded offsets, compressed offset representations, and more compact node records could significantly reduce `.bjidx` size.

* **JSONPath-style queries**: Higher-level querying could provide more convenient access to large documents without requiring manual traversal of the lazy object/list hierarchy.

## Design philosophy

ByteJSON does not try to be a faster replacement for Python's `json` module. Instead, it explores a different access model: treating a JSON document more like a random-access data store than a document that must be fully materialized before it can be queried.

```text
Traditional JSON
────────────────────────────────────────
JSON file → parse everything → Python objects
                              ↓
                        high memory use


ByteJSON
────────────────────────────────────────
JSON file → index locations → lazy access
                              ↓
                       decode only what is used
```

The goal is simple: **make large JSON documents randomly accessible without requiring the entire document to live as Python objects in memory.**

> [!WARNING]
> **Experimental prototype.** Expect APIs, index formats, and performance characteristics to change.
