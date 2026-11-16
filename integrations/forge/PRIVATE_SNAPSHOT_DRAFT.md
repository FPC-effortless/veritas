# Draft: operator-private snapshots

This additive API preserves private research inputs without claiming redistribution permission or changing existing Forge releases.

`forge_data.private_snapshot.freeze_private(root, files, spec, destination)` copies an explicit bounded file roster into a new private snapshot. `verify_private(root, manifest_sha256)` verifies the exact manifest, file set, policy and contents. The specification requires AI-use permission, a completed privacy review, explicit `redistribution_allowed=false`, and `visibility=operator_private`. These are operator declarations, not attested rights.

The snapshot has its own schema and preserves caller-defined study splits. It is **not** a temporal release, split-independence check, data-adequacy certificate or scientific qualification. Existing public `Dataset` and `verify_release` interfaces reject this schema; existing release behavior is unchanged. No export or network endpoint is added.

Bounded safeguards: explicit regular files; source/root/destination-ancestor symlinks rejected; immutable destination; hashes and byte counts; 64 MiB total bound; POSIX 0700 directories and 0600 files, checked on verification. This is not encryption or protection against a trusted filesystem operator, hostile concurrent filesystem mutation, or every future export integration. Private data must remain within its authorized boundary.

## Validation and limitations

Run from the repository root with Forge available:

```
PYTHONPATH=integrations/forge/src python -m unittest discover -s integrations/forge/tests -p test_private_snapshot.py -v
```

The included tests use constructed fixtures and check integrity, public-reader rejection, disallowed rights changes, paths, symlinks and immutable destination behavior. Additional independent adversarial checks were run privately; their data/review artifacts are not included in this source-only draft.

This is a draft integration proposal, not merged or release-qualified. It does not authorize model training, public disclosure of research evidence, or any change to source permissions.
