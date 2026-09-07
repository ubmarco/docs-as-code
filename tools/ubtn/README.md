# ubtn onboarding

This branch (`ubtn`) makes this repo buildable by ubtrace-native, whose
builder runs `ubc build html <entry>` on entry path `docs`, after resolving
and running a `ubtrace-prepare` script from `docs/ubproject.toml` (`ubc
script ubtrace-prepare --path docs`, cwd = `docs/`).

- `docs/ubproject.toml`: `ubc`'s own config (it never reads `conf.py`).
  `[needs]` mirrors `src/extensions/score_metamodel/metamodel.yaml`;
  everything else (parsers, `[lint]`, `[build.html]`, `[scripts]`) is
  hand-maintained.
- `metamodel_to_ubproject.py`: regenerates the `[needs]` block between the
  `# ===== BEGIN/END GENERATED =====` markers from `metamodel.yaml` (need
  types, the union of custom options as `[needs.fields.*]`, and link types).
  Run `python3 tools/ubtn/metamodel_to_ubproject.py` after any metamodel.yaml
  change; `--check` exits 1 without writing if it's stale.
- `ubtrace-prepare.sh`: runs `bazel run //:docs_check` (the repo's real docs
  gate) before the `ubc` build, downloading bazelisk itself if `bazel` isn't
  on PATH. `UBTN_SKIP_BAZEL=1` skips it (loudly) for local `ubc`-only
  iteration -- never use it to validate a real build. It also snapshots and
  restores `docs/ubproject.toml` around the bazel call -- see below. After a
  successful `docs_check`, it also materializes
  `@score_process_description//:needs_json_file` (resolved via `bazel
  cquery`) into `docs/_ubtn_external/process_needs.json`, gitignored, copied
  fresh on every run -- see "External needs" below.

## External needs

The S-CORE process requirements/guidelines/etc. (`gd_req__*`, `gd_guidl__*`,
`std_req__*`, `std_wp__*`, `workflow__*`, `workproduct__*`, ...) live in the
separate `eclipse-score/process_description` repo, which this fork does not
carry. Upstream feeds them into sphinx-needs purely as *data* -- via Bazel:
`BUILD`'s `docs(external_needs =
["@score_process_description//:needs_json_file"])`, backed by
`MODULE.bazel`'s `bazel_dep(name = "score_process_description", version =
"2.1.2")`. It never mounts process_description's *pages* here (its `bundles`
list has no process_description entry); links to those needs resolve to the
externally-hosted `https://eclipse-score.github.io/process_description`
site instead.

`docs/ubproject.toml` mirrors that with a `[[needs.external_needs]]` entry
pointing at `_ubtn_external/process_needs.json`, which `ubtrace-prepare.sh`
materializes (real bytes, not a symlink -- `bazel-bin`/`bazel-out` point
*outside* this worktree, and ubtrace-native's snapshot/restore round trip
would lose a symlinked reference) after every successful `bazel run
//:docs_check`. `UBTN_SKIP_BAZEL=1` skips that too, so a `ubc`-only local
iteration with no prior real run has no external needs (the script warns
loudly); `docs/_ubtn_external/` is gitignored, a runtime artifact.

Verified end to end: `ubc check docs` (`needs.dead_link` + `needs.link_ref`)
drops from 131 to 0, and `ubc query cypher "MATCH (n) RETURN count(n)"`
against `docs` goes from 69 (local only) to 1320 (69 local + 1251 external) --
`ubc` does include external needs in the query graph. Wiring them in also
surfaces `needs.link_condition_invalid` (~1290 hits) and one `needs.external`
warning, both from process_description's *own* internal links using
sphinx-needs' version-conditioned syntax (e.g. `wf__cr_mt_comparch[version==1]`),
which ubc's schema does not model; see "Known gaps". It also fully populates
two `needtable` views in `docs/internals/requirements/process_overview.rst`
and `requirements.rst` that were previously near-empty, which is why
`needs.views_max_items = 0` was added (they'd otherwise truncate at ubc's
default cap of 100, now that they match all 177 `gd_req__*` needs).

## Known gaps

- `docs/ubproject.toml` used to be gitignored upstream because
  `src/extensions/score_sync_toml` (needs-config-writer) regenerates it as a
  side effect of *any* Sphinx build, overwriting it with a dump of the live
  sphinx-needs config that has none of this branch's `[[needs.types]]`/
  `[needs.fields.*]`/`[needs.links.*]`/`[project]`/`[parse.parsers.*]`/
  `[lint]`/`[build.html]`/`[scripts]`. Since `ubtrace-prepare.sh` runs
  `bazel run //:docs_check` right before `ubc build html docs`, that
  regeneration would otherwise silently replace our config the moment the
  prepare step succeeds. `ubtrace-prepare.sh` copies `docs/ubproject.toml`
  aside before the bazel call and restores it afterwards, whatever bazel did
  to the file, so `ubc build html docs` always sees the checked-in version.

- `metamodel.yaml` writes colors as bare `color: #FEDCD2`; YAML treats
  ` #...` as a comment, so it parses as `color: None` in both the real
  score_metamodel loader and this script. Colors are simply omitted.
- `needs_types.role` collides with ubc's built-in `role` directive
  (`config.conflicting_content_model`); unused in this docs/ tree today.
- `[lint] ignore`s `needs.link_condition_invalid`/`needs.external`:
  process_description's own needs.json links some of *its* needs to each
  other using sphinx-needs' version-conditioned link syntax (e.g.
  `wf__cr_mt_comparch[version==1]` in a `satisfies`/`realizes`/... field) --
  a versioning feature ubc's schema does not model. That is entirely
  process_description's own internal linkage, not this repo's content, and
  not fixable from here. See "External needs" above (this used to ignore
  `needs.dead_link`/`needs.link_ref` instead, before external needs were
  wired in -- those now resolve and no longer fire).
- `needpie`/`needtable` `:filter-func:` (Python callables) and one
  `.startswith()` `:filter:` expression aren't portable to ubc's filter
  engine; both charts/tables still render from their remaining filters.
- No `[parse.extend_directives]` were needed -- ubc natively supports every
  directive this docs/ tree uses (sphinx-needs types/`needtable`/`needpie`/
  `needextend`, sphinx-design `grid`/`grid-item-card`, sphinxcontrib-mermaid,
  core RST).
