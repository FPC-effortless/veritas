# Forge graphical dataset workbench

Forge now has a dataset GUI alongside its independent CLI and Python API. The
workbench uses TrainLab's interface conventions and hosting controls. It provides
an immutable dataset library, guided source import, temporal data exploration,
release comparisons, file verification, exports and persistent activity.

## Start locally

From the Veritas repository root, install the sibling packages together:

```bash
python -m pip install './integrations/trainlab[server]' './integrations/forge[workbench]'
forge-workbench --workspace /absolute/path/to/forge-data
```

Open `http://127.0.0.1:8766/forge/` on that machine. Or run from source:

```bash
export PYTHONPATH="$PWD/integrations/forge/src:$PWD/integrations/trainlab/src"
python -m forge_data.workbench --workspace /absolute/path/to/forge-data
```

Local source mode needs neither network nor package installation. The optional
production mode needs the pinned Waitress server dependency. Forge's core CLI
and API still have no TrainLab runtime dependency; the optional GUI reuses the
TrainLab hosting package rather than maintaining a second authentication stack.
The candidate package versions are Forge 0.2.0 and TrainLab 0.3.0. These commands
install the checked-out packages, not an assumed published release.

## Both workbenches in one service

```bash
trainlab serve --runs /private/trainlab/runs \
  --experiments /absolute/path/to/approved-recipes \
  --forge-workspace /private/forge
```

The root URL serves TrainLab; `/forge/` serves Forge. The header's **Open Forge**
and **Open TrainLab** links switch between the actual applications. Both share
one origin and, in production mode, the same operator authentication. Each
workspace retains its own same-origin action token and background operation.
TrainLab continues to accept only approved recipe identifiers, not browser
commands. Dataset ingestion never invokes source acquisition or model training.

## Everyday workflow

1. **Create a dataset.** Choose UTF-8 JSONL, paste records, or load the clearly
   labelled constructed example. Fill in dataset/source identity, source version,
   adapter, provenance reference, license/permission reference and split salt.
   An existing spec JSON file can populate the form. Changing the source clears
   permission declarations; confirm them again or import its matching spec.
2. **Confirm source-use requirements.** AI-use permission, redistribution and
   privacy review are required operator declarations. An uploaded spec or checked
   box is not independent source attestation. The example uses constructed data.
3. **Create the immutable release.** A background job retains input bytes/spec,
   applies the existing Forge normalization and subject-disjoint split logic,
   verifies the pinned output, and adds the release to the library. Existing
   releases are never overwritten. Errors remain visible in Activity.
4. **Inspect and explore.** Open a dataset to see counts, source context, manifest
   identity and file hashes. The data explorer allows train or validation only.
   Select observation fields and a feature-availability cutoff. Actions are
   excluded. Outcomes remain hidden unless available by the chosen outcome
   cutoff. A later outcome clock never advances feature visibility.
5. **Verify and export.** Recheck every immutable release file against the saved
   manifest pin. Download the exact manifest, or export matching selected examples
   as JSONL or CSV. CSV values are escaped against common spreadsheet formula
   prefixes. Source `verified` flags are retained as reported, not promoted into
   independent verification. Long values are shortened only for on-screen display;
   exports retain the full selected values.
6. **Compare releases.** Select two to eight library entries. Compare source
   versions/hashes, adapter/split declarations and record counts. Download the
   comparison as JSON. The comparison declares differences, not scientific winners.

Operations use UTC timestamps; decoded robot sources use nonnegative relative
seconds. TEST rows are withheld across the GUI preview/export APIs. Only their
aggregate counts and file hashes are shown. The core API's explicit local TEST
opt-in remains separate; the GUI does not add authorization for private panels.

## Source format

The existing `operations-jsonl` and `robot-jsonl` adapters remain authoritative.
Operations records require `episode_id`, `subject_id`, `record_id`, `observed_at`,
`available_at`, and an observation object. Optional actions/outcomes follow the
core schema. Robot records use `time_seconds`, `available_seconds` and frame
metadata. Missing outcomes stay unknown. Duplicate keys, nonfinite JSON and
excessively nested input are rejected by the GUI ingestion boundary.

The **Load constructed example** action fills a local 30-record sensor source
and a fixture-only source spec. It does not fetch publisher data, perform
training, or confer qualification. Its normal split is 24 train / 3 validation /
3 local TEST records. The **Create immutable release** button runs the real
Forge implementation; the GUI is not a transcript or test-output viewer.

## Bounds and persistence

- Source uploads: at most 8 MiB of original UTF-8 bytes and 20,000 records.
  Browser uploads encode the original bytes as base64 so quote/backslash-heavy
  JSONL fits the bounded 12 MiB request envelope without changing source hashes.
- Library: at most 128 releases and 1,024 retained activity records per workspace.
  Archive/rotate full workspaces offline before these limits. One service owns
  each writable workspace; concurrent service replicas sharing it are unsupported.
- Explorer: first 128 common train/validation observation fields, up to 12 selected
  fields, and up to 50 rows per page. The GUI uses 25-row pages. A cell displays
  at most 512 characters with a truncation notice; source bytes and exports are
  unchanged. The CLI supports wider schemas under its own release bounds.
- One creation or integrity-verification operation runs at a time in Forge.
  TrainLab's approved experiment executor remains a separate bounded operation.
  No browser-supplied shell command, URL acquisition or arbitrary filesystem path
  is accepted. Failed/unfinished operations are retained; a restart never invents
  success or automatically resumes work.
- Metadata is private and written using TrainLab's existing fsync/atomic-replace
  helper. Immutable release files use Forge's existing staging/rename protocol.
  A crash can leave an unlisted source/release or unfinished job. Stop the service,
  inspect the workspace and archive incomplete work before operator recovery.

Workspace layout:

```text
forge-data/
  sources/<release-id>/source.jsonl, spec.json
  releases/<release-id>/manifest.json, train.jsonl, validation.jsonl, test.jsonl
  metadata/<release-id>.json
  jobs/<operation-id>.json
```

Pins stored at release creation bind every later detail/preview/export/compare
read through `Dataset`. The library's badge describes the last recorded integrity
check, not a continuously authenticated source. Editing both local metadata and
files is outside file-integrity attestation. Use filesystem access control and
backups appropriate to the original source's rights and privacy policy.

## Authenticated production hosting

Use the same controls and operator trust model as
[TrainLab production hosting](../trainlab/PRODUCTION.md):

```bash
trainlab init-auth /private/users.json --username operator
trainlab serve --production --auth-file /private/users.json \
  --public-origin https://lab.example.com \
  --runs /private/trainlab/runs --forge-workspace /private/forge
```

For a standalone Forge service:

```bash
forge-workbench --production --auth-file /private/users.json \
  --public-origin https://forge.example.com --workspace /private/forge
```

Bind the backend to loopback behind an HTTPS reverse proxy for remote users.
For standalone hosting, proxy port 8766 rather than the shared service port 8765.
The existing non-root/read-only TrainLab image contains both packages; its default
command and Compose template enable Forge at `/forge/`. The Caddy template allows
12 MiB request bodies for dataset uploads. TrainLab's command API retains its
separate 4 KiB application-level limit. All Forge assets/APIs require production
operator authentication; Host/Origin and per-workspace action tokens also apply.
The shared workspace is for trusted operators, without tenant or role isolation.

The combined `/healthz` contains aggregate Forge health without source records,
commands, credentials or tokens. Low free space, unreadable metadata or recorded
integrity failures degrade Forge health. It does not prove external TLS, source
permissions, continuous byte integrity or job liveness. Configure storage quotas,
alerts, identity/access policy and deployment acceptance on the actual host.

TrainLab's `backup` command covers its finalized run store; it **does not** back
up Forge's separate source/release workspace. Stop both workspaces and all writers,
then take an encrypted/access-controlled filesystem snapshot of the entire Forge
workspace and record its snapshot identity separately. Test restoration to a new
location, start against that restored location, and re-run integrity checks on
all releases before trusting it. Keep source permissions and credentials under
their separate retention policy. Roll back the exact reviewed image/source and
its separately verified workspace snapshot; never overwrite the only data copy.

## Verification and evidence

```bash
export PYTHONPATH="$PWD/integrations/forge/src:$PWD/integrations/trainlab/src"
python -m unittest discover -s integrations/forge/tests -v
python -m unittest discover -s integrations/forge/tests_workbench -v
python -m unittest discover -s integrations/trainlab/tests -v
python integrations/forge/tests_workbench/browser_smoke.py --evidence /tmp/forge-gui-evidence
```

The browser check requires installed Playwright/Chromium and the production server
extra. It drives the real authenticated combined service through source creation,
file/spec upload, visibility controls, exports, verification, errors, comparison,
workbench switching and desktop/mobile views. Video/screenshots and raw artifacts
are retained when `--evidence` names a new directory. It uses constructed records
only. CI runs package/hosting contracts on Python 3.11/3.13 and actual browser
acceptance on 3.13. A passing constructed run is implementation evidence;
scientific, authentic-source, release and installed-host acceptance remain separate.
