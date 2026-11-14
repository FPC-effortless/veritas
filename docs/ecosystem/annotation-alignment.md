# Check annotation coordinates against pinned media

Forge checks pixel boxes in supported PNG assets and frame intervals in
PCM WAVE audio. Each rule binds a declared media feature to an annotation
feature. The input is a pinned Forge diagnostic view. The complete view
must contain only train and validation records.

```json
{
  "schema": "forge.annotation-alignment-rules.v1",
  "rules": [
    {"media": "image", "annotations": "boxes", "format": "png"},
    {"media": "recording", "annotations": "segments", "format": "wav"}
  ]
}
```

Each media value contains a relative `path` and a `sha256` of the exact
bytes. The annotation feature is an array of up to 512 coordinate arrays.
An empty array declares no annotations. Use zero-based half-open integer
coordinates in pixels or frames.

| Format | Shape | Bounds |
| --- | --- | --- |
| PNG | `[left, top, right, bottom]` | Positive width and height. The right and bottom endpoints may equal the validated image dimensions. |
| PCM WAVE | `[start, end]` | Positive interval length. The end may equal the validated frame count. A stereo frame includes both channels. |

```bash
python -m forge_data.annotation_alignment --view view.json --sha256 VIEW_SHA --rules rules.json --rules-sha256 RULES_SHA --media-root ./assets
```

Asset reads use the existing PNG and WAV validity rules and enforce both
per-file and aggregate byte budgets. The report distinguishes invalid
coordinates, out-of-bounds annotations, bad or changed media, and
unavailable coverage. Findings retain row, field, annotation index and
reason. Media bytes, paths and coordinate values are omitted.

Format support matches the bounded semantic audit profiles. A skipped
row suffix, unsupported media or exhausted read allowance is visible.
An observed failure remains a failure even when part of the view is
unchecked. The audit checks bounds on a stable local media snapshot.
Whether a box encloses the intended object or an interval marks the
intended event requires independent annotation evidence.
