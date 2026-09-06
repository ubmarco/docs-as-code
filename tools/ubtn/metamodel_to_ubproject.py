#!/usr/bin/env python3
"""Regenerate the metamodel-derived part of docs/ubproject.toml.

This repo's need types, extra options, and link types are defined once, in
src/extensions/score_metamodel/metamodel.yaml, and consumed by
src/extensions/score_metamodel/yaml_parser.py to configure sphinx-needs for
the Bazel/Sphinx build. `ubc` (the ubtrace-native doc builder) does not read
conf.py or metamodel.yaml at all -- it has its own config file,
docs/ubproject.toml, with its own (simpler) [needs] schema.

To keep the two in sync without hand-editing ubproject.toml every time a need
type is added, this script re-implements the same defaulting rules as
yaml_parser.py (prefix defaulting, the default-option exclusion list, and the
per-type option/link unions) and regenerates ONLY the block of
docs/ubproject.toml between the

    # ===== BEGIN GENERATED ... =====
    # ===== END GENERATED =====

markers. Everything else in the file (parsers, extend_directives, lint,
scripts, project metadata, ...) is left untouched.

Usage:
    python3 tools/ubtn/metamodel_to_ubproject.py [--check]

    --check   Do not write; exit 1 if the generated block would change
              (useful in CI to catch a metamodel.yaml edit that was not
              followed by re-running this script).

Requires PyYAML (`pip install pyyaml`) unless the interpreter already has it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print(
        "error: this script needs PyYAML to parse metamodel.yaml.\n"
        "       install it with:  pip install pyyaml\n"
        "       (or: pip install --user pyyaml)",
        file=sys.stderr,
    )
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
METAMODEL_PATH = REPO_ROOT / "src/extensions/score_metamodel/metamodel.yaml"
UBPROJECT_PATH = REPO_ROOT / "docs/ubproject.toml"

BEGIN_MARKER = (
    "# ===== BEGIN GENERATED (tools/ubtn/metamodel_to_ubproject.py) "
    "- do not edit below by hand ====="
)
END_MARKER = "# ===== END GENERATED ====="


def default_options() -> set[str]:
    """Sphinx/sphinx-needs built-in option names.

    Mirrors src/extensions/score_metamodel/yaml_parser.py::default_options()
    exactly. These are never turned into custom `[needs.fields.*]` entries,
    because sphinx-needs (and ubc) already know about them natively.
    """
    return {
        "target_id",
        "id",
        "status",
        "docname",
        "lineno",
        "type",
        "lineno_content",
        "doctype",
        "content",
        "type_name",
        "type_color",
        "type_style",
        "title",
        "full_title",
        "layout",
        "template",
        "id_parent",
        "id_complete",
        "external_css",
        "sections",
        "section_name",
        "type_prefix",
        "constraints_passed",
        "collapse",
        "hide",
        "delete",
        "jinja_content",
        "is_part",
        "is_need",
        "is_external",
        "is_modified",
        "modifications",
        "has_dead_links",
        "has_forbidden_dead_links",
        "tags",
        "arch",
        "parts",
        "is_import",
        "constraints",
        # Built-in generic link field, always present in sphinx-needs; never
        # declared as a custom link type.
        "links",
    }


def load_metamodel(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise SystemExit(f"error: {path} did not parse to a mapping")
    return data


def build_types(needs_types: dict[str, Any]) -> list[dict[str, Any]]:
    """One [[needs.types]] entry per metamodel need type.

    prefix defaulting mirrors yaml_parser.py::_parse_need_type: an explicit
    `prefix:` wins, otherwise the prefix is `<directive>__`.
    """
    types: list[dict[str, Any]] = []
    for directive, spec in needs_types.items():
        if not isinstance(spec, dict):
            raise SystemExit(f"error: needs_types.{directive} is not a mapping")
        prefix = spec.get("prefix", f"{directive}__")
        entry: dict[str, Any] = {
            "directive": directive,
            "title": spec["title"],
            "prefix": prefix,
        }
        # metamodel.yaml writes colors as bare `color: #FEDCD2` (no quotes).
        # In YAML a "#" preceded by whitespace starts a comment, so every
        # such value parses as None -- this is true of the real metamodel
        # loader (yaml_parser.py) too, not just this script. Treat a
        # None/missing color as "not set" rather than emitting an invalid
        # `color = null`.
        if spec.get("color") is not None:
            entry["color"] = spec["color"]
        if spec.get("style") is not None:
            entry["style"] = spec["style"]
        types.append(entry)
    return types


def build_fields(
    needs_types: dict[str, Any], base_optional_options: dict[str, Any]
) -> list[str]:
    """Union of every mandatory/optional option name used by any need type,
    plus the globally-added base options, minus sphinx-needs built-ins.

    Mirrors yaml_parser.py::_collect_all_custom_options. Per-type
    mandatory-vs-optional and per-type applicability are not modelled here:
    ubc's [needs.fields.*] are global, not scoped to a need type, so (as
    directed) we take the union.
    """
    defaults = default_options()
    all_options: set[str] = set(base_optional_options.keys())
    for directive, spec in needs_types.items():
        if not isinstance(spec, dict):
            raise SystemExit(f"error: needs_types.{directive} is not a mapping")
        all_options.update((spec.get("mandatory_options") or {}).keys())
        all_options.update((spec.get("optional_options") or {}).keys())
    return sorted(all_options - defaults)


def build_links(
    needs_types: dict[str, Any], needs_extra_links: dict[str, Any]
) -> list[tuple[str, str, str]]:
    """(name, incoming, outgoing) for every link type.

    Starts from needs_extra_links (in metamodel.yaml declaration order), then
    appends any link name used in a type's mandatory_links/optional_links
    that metamodel.yaml never declared under needs_extra_links (a metamodel
    gap we paper over rather than fail the build on) using sphinx-needs'
    own default incoming/outgoing convention: outgoing=<name>,
    incoming=<name>_back.
    """
    defaults = default_options()  # excludes the built-in "links" field
    links: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for name, spec in needs_extra_links.items():
        links.append((name, spec["incoming"], spec["outgoing"]))
        seen.add(name)

    used: set[str] = set()
    for directive, spec in needs_types.items():
        if not isinstance(spec, dict):
            continue
        used.update((spec.get("mandatory_links") or {}).keys())
        used.update((spec.get("optional_links") or {}).keys())

    for name in sorted(used - seen - defaults):
        links.append((name, f"{name}_back", name))

    return links


def toml_str(s: str) -> str:
    """A TOML basic string literal for s. json.dumps' escaping is a safe
    superset for the plain-ASCII titles/colors this metamodel uses."""
    return json.dumps(s)


def render_generated_block(
    types: list[dict[str, Any]],
    fields: list[str],
    links: list[tuple[str, str, str]],
) -> str:
    lines: list[str] = [BEGIN_MARKER, "# Regenerate with: python3 tools/ubtn/metamodel_to_ubproject.py", ""]

    lines.append("# Need types, derived from src/extensions/score_metamodel/metamodel.yaml needs_types.")
    for t in types:
        lines.append("[[needs.types]]")
        lines.append(f"directive = {toml_str(t['directive'])}")
        lines.append(f"title = {toml_str(t['title'])}")
        lines.append(f"prefix = {toml_str(t['prefix'])}")
        if "color" in t:
            lines.append(f"color = {toml_str(t['color'])}")
        if "style" in t:
            lines.append(f"style = {toml_str(t['style'])}")
        lines.append("")

    lines.append(
        "# Extra need options, derived from the union of all mandatory_options/optional_options\n"
        "# across needs_types (plus needs_types_base_options) in metamodel.yaml, minus the\n"
        "# sphinx-needs built-in option names. ubc's fields are global (not per-type), so a\n"
        "# per-type mandatory/optional distinction is not representable here; every custom\n"
        "# option used anywhere becomes an optional string field."
    )
    for name in fields:
        lines.append(f"[needs.fields.{name}]")
        lines.append('schema.type = "string"')
        lines.append("")

    lines.append("# Link types, derived from needs_extra_links in metamodel.yaml (plus any link name")
    lines.append("# used in a type's mandatory_links/optional_links but not declared there).")
    for name, incoming, outgoing in links:
        lines.append(f"[needs.links.{name}]")
        lines.append(f"incoming = {toml_str(incoming)}")
        lines.append(f"outgoing = {toml_str(outgoing)}")
        lines.append("")

    lines.append(END_MARKER)
    # Join and ensure exactly one trailing newline, no trailing blank lines.
    text = "\n".join(lines)
    return text.rstrip("\n") + "\n"


def splice(existing_text: str, generated_block: str) -> str:
    if BEGIN_MARKER not in existing_text or END_MARKER not in existing_text:
        raise SystemExit(
            f"error: {UBPROJECT_PATH} has no generated-block markers.\n"
            f"       Add these two lines where the generated [needs] content should go:\n"
            f"         {BEGIN_MARKER}\n"
            f"         {END_MARKER}"
        )
    pre, rest = existing_text.split(BEGIN_MARKER, 1)
    _, post = rest.split(END_MARKER, 1)
    return pre + generated_block + post.lstrip("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="don't write; exit 1 if the generated block is out of date",
    )
    args = parser.parse_args()

    if not METAMODEL_PATH.is_file():
        raise SystemExit(f"error: metamodel not found at {METAMODEL_PATH}")
    if not UBPROJECT_PATH.is_file():
        raise SystemExit(f"error: ubproject.toml not found at {UBPROJECT_PATH}")

    data = load_metamodel(METAMODEL_PATH)
    needs_types = data.get("needs_types", {}) or {}
    needs_extra_links = data.get("needs_extra_links", {}) or {}
    base_optional_options = (data.get("needs_types_base_options", {}) or {}).get(
        "optional_options", {}
    ) or {}

    types = build_types(needs_types)
    fields = build_fields(needs_types, base_optional_options)
    links = build_links(needs_types, needs_extra_links)

    generated_block = render_generated_block(types, fields, links)

    existing_text = UBPROJECT_PATH.read_text(encoding="utf-8")
    new_text = splice(existing_text, generated_block)

    if new_text == existing_text:
        print(f"{UBPROJECT_PATH}: already up to date "
              f"({len(types)} types, {len(fields)} fields, {len(links)} links)")
        return 0

    if args.check:
        print(f"{UBPROJECT_PATH}: out of date, run without --check to regenerate", file=sys.stderr)
        return 1

    UBPROJECT_PATH.write_text(new_text, encoding="utf-8")
    print(f"{UBPROJECT_PATH}: regenerated "
          f"({len(types)} types, {len(fields)} fields, {len(links)} links)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
