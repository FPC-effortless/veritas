# Verify who signed an offline diagnostic bundle review

A signed review binds a signer, verdict, note, pack identities and exact bundle
manifest. It is separate from the diagnostic bundle so recipients can exchange
one or more reviews without changing the bundle being reviewed.

Use a local OpenSSH signing key and distribute the allowed-signers trust file
and its SHA256 through a trusted channel. A simple exact-principal entry
contains an identity followed by its SSH public key:

```text
researcher@example.org ssh-ed25519 PUBLIC_KEY_BYTES
```

Create a review envelope outside the bundle directory:

```bash
python -m trainlab.signed_bundle_review sign \
  --root bundle --manifest-sha256 BUNDLE_SHA \
  --signer researcher@example.org --key /path/to/signing-key \
  --verdict accept --note 'Reviewed the displayed findings' > review.json
```

The recipient verifies the signature using the expected signer and separately
retained bundle and trust-list hashes:

```bash
python -m trainlab.signed_bundle_review verify \
  --root bundle --manifest-sha256 BUNDLE_SHA --envelope review.json \
  --signer researcher@example.org --allowed-signers allowed_signers \
  --allowed-signers-sha256 TRUST_SHA
```

The signing message is canonical finite JSON under the fixed OpenSSH namespace
`veritas-diagnostic-review-v1`. The bundle is verified into a byte snapshot.
The pack list is derived from that snapshot, and the receipt records its IDs
and versions in bundle order. Verification rejects a changed manifest, modified
receipt, wrong namespace, untrusted key or wrong expected identity. The
OpenSSH process runs with a bounded timeout and never gets arguments from a
pack or a finding. The local process environment must supply a trusted
`ssh-keygen`.

A verified signature identifies a key authorized by the recipient's trust
list. Establishing the relationship between that key and a person, revoking
compromised keys, and distributing updated trust lists remain operator duties.
A signed verdict does not attest the truth of imported reports and does not
replace repository review or scientific qualification. This workflow has no
online identity service or executable pack loader.
