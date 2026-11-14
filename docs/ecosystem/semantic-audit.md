# Audit declared feature semantics in Forge

Run alongside the existing exact-content and quality diagnostics on a pinned
Forge diagnostic view. The entire bounded input is checked for schema validity
and train/validation scope before any row-prefix scan. Extra feature keys
outside the view's field declaration are rejected across the full input. Each finding identifies
the row, field and failed constraint without copying the row's feature values.

```bash
python -m forge_data.semantic_audit \
  --input view.json --sha256 VIEW_SHA \
  --rules rules.json --rules-sha256 RULES_SHA \
  --media-root ./assets
```

The rule document uses this schema:

```json
{
  "schema": "forge.semantic-rules.v1",
  "fields": {
    "distance": {
      "type": "number",
      "min": 0,
      "max": 100,
      "unit": {"field": "distance_unit", "symbol": "m"}
    },
    "note": {"type": "string", "required": false, "nullable": true},
    "recording": {"type": "file", "format": "wav"}
  }
}
```

Field types are `number`, `integer`, `string`, `boolean`, `object`, `array`
and `file`. Fields default to required and nonnullable. Numeric bounds are
inclusive. `enum` uses exact typed JSON equality. A unit check compares the
actual value of a separate declared field to a literal symbol. It does not infer
or convert units or verify measurement truth.

A file value has exactly `path` and `sha256`. Paths must be relative to the
supplied local media root, with no traversal or symlinks. Each file read is
bounded and pinned by its bytes. Supported checks are:

| Format | Checks |
| --- | --- |
| `utf8` | Decodes as UTF-8, nonblank and without NUL bytes |
| `json` | Valid UTF-8 finite JSON, unique object keys, bounded nesting |
| `csv` | UTF-8, strict CSV syntax, distinct nonblank headers and consistent row width |
| `png` | PNG structure, chunk CRCs and bounded scanline decoding for noninterlaced 8-bit grayscale and truecolor images, with or without alpha, with no ancillary chunks and an exact compressed stream |
| `wav` | RIFF/WAVE envelope, chunk bounds and padding, consistent PCM metadata, and nonempty frame-aligned PCM data |

Files above 4 MiB, PNG profiles outside the supported decoding subset, non-PCM WAV formats, and
unavailable or exhausted media reads are tracked as unchecked. The aggregate
read budget defaults to 32 MiB. Repeated references to the same path, hash and
format reuse their result within the scan. Use a stable local snapshot. This
workflow does not defend against concurrent hostile replacement of files.

A result is `FAILED` if any tested rule failed, `NOT_RUN` if zero rows were
scanned, and `INCONCLUSIVE` if part of the scan was not covered and no failure
was observed. `TESTED` covers the declared rules on the complete selected view.
Undeclared fields are visible in the scope. Limiting displayed findings leaves
the total count intact. Object/array semantics are shallow type and enum checks.
Alignment between media and annotations, additional media formats, and domain
truth require separate checks.
