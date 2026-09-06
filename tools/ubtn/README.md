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
  restores `docs/ubproject.toml` around the bazel call -- see below.

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
- `[lint] ignore`s `needs.dead_link`/`needs.link_ref`: ~100 `tool_req__*`
  needs `:satisfies:` process needs (`gd_req__*`/`gd_guidl__*`) that live in
  the separate `process_description` repo, out of scope here.
- `needpie`/`needtable` `:filter-func:` (Python callables) and one
  `.startswith()` `:filter:` expression aren't portable to ubc's filter
  engine; both charts/tables still render from their remaining filters.
- No `[parse.extend_directives]` were needed -- ubc natively supports every
  directive this docs/ tree uses (sphinx-needs types/`needtable`/`needpie`/
  `needextend`, sphinx-design `grid`/`grid-item-card`, sphinxcontrib-mermaid,
  core RST).
