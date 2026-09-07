#!/usr/bin/env bash
# ubtrace-native "prepare" step for this repo.
#
# ubtrace-native's builder resolves the `ubtrace-prepare` script from
# docs/ubproject.toml and runs it (via `ubc script ubtrace-prepare`) BEFORE
# `ubc build html docs`. This repo's real quality gate for the docs is its
# own Bazel check, `bazel run //:docs_check` (see BUILD at the repo root) --
# it runs score_metamodel's sphinx-needs checks, the RST file-based tests,
# and everything else the Bazel docs build wires up, none of which `ubc`
# itself knows how to run. So: this script's whole job is to run that check
# and fail loudly if it fails, gating the ubc HTML build on the same
# correctness bar the upstream repo already enforces in CI.
#
# The ubtrace-native build container is Amazon Linux 2023: it has curl, git,
# python3 and network access, but no bazel preinstalled. So if `bazel` is not
# already on PATH, this script downloads bazelisk (which in turn fetches the
# exact Bazel version pinned in .bazelversion) into a small cache dir and
# uses that instead of failing outright.
#
# IMPORTANT: this repo's own src/extensions/score_sync_toml extension
# (needs-config-writer) regenerates docs/ubproject.toml as a side effect of
# ANY Sphinx build it runs, including `bazel run //:docs_check` -- that is
# why docs/ubproject.toml is normally gitignored upstream. Its regenerated
# version has none of the [[needs.types]]/[needs.fields.*]/[needs.links.*]/
# [project]/[parse.parsers.*]/[lint]/[build.html]/[scripts] this ubtn branch
# needs (see tools/ubtn/README.md), so if left in place it would silently
# break the `ubc build html docs` step that runs right after this script.
# We snapshot the checked-in docs/ubproject.toml before running bazel and
# restore it afterwards so that side effect never reaches the ubc build.
set -euo pipefail

# --- resolve repo root from this script's own location, not the caller's cwd ---
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")" >/dev/null 2>&1 && pwd -P)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." >/dev/null 2>&1 && pwd -P)"

log() {
    printf '[ubtrace-prepare] %s\n' "$*" >&2
}

step_start_ts=$(date +%s)
step() {
    local now
    now=$(date +%s)
    log "(+${now}-${step_start_ts}s=$((now - step_start_ts))s) $*"
    step_start_ts=${now}
}

log "repo root: ${REPO_ROOT}"

# --- escape hatch for local ubc-only iteration ---
if [ "${UBTN_SKIP_BAZEL:-0}" = "1" ]; then
    log "############################################################"
    log "# WARNING: UBTN_SKIP_BAZEL=1 -- skipping 'bazel run //:docs_check'."
    log "# The real docs quality gate did NOT run. Do not treat a build"
    log "# produced this way as validated; this is for local ubc-only"
    log "# iteration ONLY. Unset UBTN_SKIP_BAZEL before a real build."
    log "############################################################"
    if [ ! -f "${REPO_ROOT}/docs/_ubtn_external/process_needs.json" ]; then
        log "############################################################"
        log "# WARNING: docs/_ubtn_external/process_needs.json does not exist,"
        log "# and UBTN_SKIP_BAZEL=1 skips the bazel step that would materialize"
        log "# it. External process needs (gd_req__*/gd_guidl__*/std_req__*/...)"
        log "# will be MISSING from this build; the docs/ubproject.toml"
        log "# [[needs.external_needs]] entry will not resolve, and"
        log "# needs.dead_link warnings for :satisfies:/:need: references into"
        log "# process_description will reappear. The build proceeds anyway --"
        log "# this is expected for local ubc-only iteration."
        log "############################################################"
    fi
    exit 0
fi

# --- find or fetch bazel ---
BAZELISK_VERSION="v1.22.1"
CACHE_DIR="${UBTN_CACHE_DIR:-${REPO_ROOT}/.ubtn-cache}"
BAZEL_BIN=""

if command -v bazel >/dev/null 2>&1; then
    BAZEL_BIN="$(command -v bazel)"
    log "using existing bazel on PATH: ${BAZEL_BIN} ($(bazel --version 2>/dev/null || true))"
else
    step "bazel not on PATH; preparing bazelisk ${BAZELISK_VERSION} in ${CACHE_DIR}"

    case "$(uname -s)" in
        Linux) os="linux" ;;
        Darwin) os="darwin" ;;
        *)
            log "error: unsupported OS '$(uname -s)' for bazelisk auto-download"
            exit 1
            ;;
    esac

    case "$(uname -m)" in
        x86_64 | amd64) arch="amd64" ;;
        aarch64 | arm64) arch="arm64" ;;
        *)
            log "error: unsupported architecture '$(uname -m)' for bazelisk auto-download"
            exit 1
            ;;
    esac

    mkdir -p "${CACHE_DIR}"
    BAZEL_BIN="${CACHE_DIR}/bazelisk-${BAZELISK_VERSION}-${os}-${arch}"

    if [ ! -x "${BAZEL_BIN}" ]; then
        url="https://github.com/bazelbuild/bazelisk/releases/download/${BAZELISK_VERSION}/bazelisk-${os}-${arch}"
        log "downloading ${url}"
        tmp="${BAZEL_BIN}.tmp.$$"
        curl -fsSL --retry 3 -o "${tmp}" "${url}"
        chmod +x "${tmp}"
        mv "${tmp}" "${BAZEL_BIN}"
    else
        log "reusing cached bazelisk at ${BAZEL_BIN}"
    fi

    log "bazelisk ready: ${BAZEL_BIN} (will fetch Bazel $(cat "${REPO_ROOT}/.bazelversion" 2>/dev/null || echo '?') on first use)"
fi

step "bazel resolved"

# --- snapshot the checked-in ubproject.toml before it can be regenerated ---
UBPROJECT="${REPO_ROOT}/docs/ubproject.toml"
UBPROJECT_BACKUP="${UBPROJECT}.ubtn-prepare-backup"
if [ -f "${UBPROJECT}" ]; then
    cp -p "${UBPROJECT}" "${UBPROJECT_BACKUP}"
fi

# --- run the repo's own docs check ---
log "running: bazel run //:docs_check   (cwd=${REPO_ROOT})"

# NB: the docs_check invocation is the condition of an `if`, not a bare
# statement, specifically so that `set -e` does not short-circuit this
# script the instant it fails -- we want to log and exit with its status
# ourselves, below.
if (
    cd "${REPO_ROOT}"
    export USE_BAZEL_VERSION
    USE_BAZEL_VERSION="$(cat .bazelversion 2>/dev/null || true)"
    "${BAZEL_BIN}" run //:docs_check
); then
    docs_check_status=0
else
    docs_check_status=$?
fi

step "bazel run //:docs_check finished with status ${docs_check_status}"

# --- restore ubproject.toml regardless of outcome: see the note at the top ---
if [ -f "${UBPROJECT_BACKUP}" ]; then
    if ! cmp -s "${UBPROJECT_BACKUP}" "${UBPROJECT}" 2>/dev/null; then
        log "docs/ubproject.toml was regenerated by the Bazel/Sphinx build (needs-config-writer) -- restoring the checked-in ubtn version."
    fi
    mv "${UBPROJECT_BACKUP}" "${UBPROJECT}"
fi

if [ "${docs_check_status}" -ne 0 ]; then
    log "docs_check FAILED (status ${docs_check_status}) -- failing the prepare step so the build does not proceed."
    exit "${docs_check_status}"
fi

log "docs_check passed."

# --- materialize score_process_description's external needs into the tree ---
#
# docs/ubproject.toml's [[needs.external_needs]] "json_path" is a LOCAL file
# path (relative to docs/). Bazel would happily hand us
# bazel-bin/external/score_process_description+/needs.json, but bazel-bin
# (like every other bazel-* convenience symlink, and bazel-out underneath it)
# is a symlink pointing OUTSIDE this worktree, into Bazel's output_base / disk
# cache. That is fine for a `ubc build html docs` run immediately afterwards
# in the SAME container (the symlink target still exists) -- but
# ubtrace-native tars this tree into a snapshot that is restored on Lambda,
# where that symlink target does not exist. The resident LSP preview/query
# would then silently lose every gd_req__*/gd_guidl__*/std_req__*/...
# external need. So: resolve the real file via Bazel and copy the actual
# bytes into the tree, rather than leaving a path that only resolves here.
EXTERNAL_NEEDS_DIR="${REPO_ROOT}/docs/_ubtn_external"
EXTERNAL_NEEDS_JSON="${EXTERNAL_NEEDS_DIR}/process_needs.json"
EXTERNAL_NEEDS_TARGET="@score_process_description//:needs_json_file"

mkdir -p "${EXTERNAL_NEEDS_DIR}"

needs_json_rel=""
if needs_json_rel="$(
    cd "${REPO_ROOT}"
    export USE_BAZEL_VERSION
    USE_BAZEL_VERSION="$(cat .bazelversion 2>/dev/null || true)"
    "${BAZEL_BIN}" cquery --output=files "${EXTERNAL_NEEDS_TARGET}" 2>/dev/null | tail -n1
)" && [ -n "${needs_json_rel}" ]; then
    # cquery only resolves the label to its would-be output path; make sure
    # the action has actually run so the file exists on disk (usually a
    # no-op cache hit, since docs_check already built it as a dependency).
    (
        cd "${REPO_ROOT}"
        export USE_BAZEL_VERSION
        USE_BAZEL_VERSION="$(cat .bazelversion 2>/dev/null || true)"
        "${BAZEL_BIN}" build "${EXTERNAL_NEEDS_TARGET}" >/dev/null 2>&1
    ) || true
fi

if [ -n "${needs_json_rel}" ] && [ -f "${REPO_ROOT}/${needs_json_rel}" ]; then
    cp -f "${REPO_ROOT}/${needs_json_rel}" "${EXTERNAL_NEEDS_JSON}"
    log "materialized external process needs: ${needs_json_rel} -> docs/_ubtn_external/process_needs.json ($(wc -c <"${EXTERNAL_NEEDS_JSON}") bytes)"
elif [ -f "${EXTERNAL_NEEDS_JSON}" ]; then
    log "############################################################"
    log "# WARNING: could not re-resolve ${EXTERNAL_NEEDS_TARGET} via 'bazel"
    log "# cquery' this run -- keeping the previously materialized"
    log "# docs/_ubtn_external/process_needs.json as-is (it may be stale)."
    log "############################################################"
else
    log "############################################################"
    log "# WARNING: could not resolve/build ${EXTERNAL_NEEDS_TARGET}."
    log "# docs/_ubtn_external/process_needs.json is MISSING -- external"
    log "# process needs (gd_req__*/gd_guidl__*/std_req__*/...) will be"
    log "# absent from this build; needs.dead_link warnings for :satisfies:/"
    log "# :need: references into process_description will reappear. The"
    log "# build proceeds anyway; externals are just missing."
    log "############################################################"
fi

step "external process needs materialized"
