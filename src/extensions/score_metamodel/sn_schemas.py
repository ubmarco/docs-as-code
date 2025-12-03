import json
from pathlib import Path

from sphinx.application import Sphinx
from sphinx.config import Config
from sphinx_needs import logging

from src.extensions.score_metamodel.yaml_parser import MetaModelData

SN_ARRAY_FIELDS = {
    "tags",
    "sections",
}

IGNORE_FIELDS = {
    "content",  # not yet available in ubCode
}

LOGGER = logging.get_logger(__name__)


def write_sn_schemas(app: Sphinx, metamodel: MetaModelData) -> None:
    config: Config = app.config
    schemas = []
    schema_definitions = {"schemas": schemas}

    for need_type in metamodel.needs_types:
        mandatory_fields = need_type.get("mandatory_options", {})
        optional_fields = need_type.get("optional_options", {})
        mandatory_links = need_type.get("mandatory_links", {})
        optional_links = need_type.get("optional_links", {})

        if not (
            mandatory_fields or optional_fields or mandatory_links or optional_links
        ):
            continue

        mandatory_links_regexes = {}
        mandatory_links_targets = {}
        optional_links_regexes = {}
        optional_links_targets = {}
        value: str
        field: str
        for field, value in mandatory_links.items():
            link_values = [v.strip() for v in value.split(",")]
            for link_value in link_values:
                if link_value.startswith("^"):
                    if field in mandatory_links_regexes:
                        LOGGER.error(
                            "Multiple regex patterns for mandatory link field "
                            f"'{field}' in need type '{type_name}'. "
                            "Only the first one will be used in the schema."
                        )
                    mandatory_links_regexes[field] = link_value
                else:
                    mandatory_links_targets[field] = link_value

        for field, value in optional_links.items():
            link_values = [v.strip() for v in value.split(",")]
            for link_value in link_values:
                if link_value.startswith("^"):
                    if field in optional_links_regexes:
                        LOGGER.error(
                            "Multiple regex patterns for optional link field "
                            f"'{field}' in need type '{type_name}'. "
                            "Only the first one will be used in the schema."
                        )
                    optional_links_regexes[field] = link_value
                else:
                    optional_links_targets[field] = link_value

        type_schema = {
            "id": f"need-type-{need_type['directive']}",
            "severity": "violation",
            "message": "Need does not conform to S-CORE metamodel",
        }
        type_name = need_type["directive"]

        selector = {
            "properties": {"type": {"const": type_name}},
            "required": ["type"],
        }
        type_schema["select"] = selector

        type_schema["validate"] = {}
        validator_local = {
            "properties": {},
            "required": [],
            # "unevaluatedProperties": False,
        }
        for field, pattern in mandatory_fields.items():
            if field in IGNORE_FIELDS:
                continue
            validator_local["required"].append(field)
            validator_local["properties"][field] = get_field_pattern_schema(
                field, pattern
            )
        for field, pattern in optional_fields.items():
            if field in IGNORE_FIELDS:
                continue
            validator_local["properties"][field] = get_field_pattern_schema(
                field, pattern
            )
        for field, pattern in mandatory_links_regexes.items():
            validator_local["properties"][field] = {
                "type": "array",
                "minItems": 1,
            }
            validator_local["required"].append(field)
            # validator_local["properties"][field] = get_array_pattern_schema(pattern)
        for field, pattern in optional_links_regexes.items():
            validator_local["properties"][field] = {
                "type": "array",
            }
            # validator_local["properties"][field] = get_array_pattern_schema(pattern)

        type_schema["validate"]["local"] = validator_local

        validator_network = {}
        for field, target_type in mandatory_links_targets.items():
            link_validator = {
                "items": {
                    "local": {
                        "properties": {"type": {"type": "string", "const": target_type}}
                    }
                },
            }
            # validator_network[field] = link_validator
        for field, target_type in optional_links_targets.items():
            link_validator = {
                "items": {
                    "local": {
                        "properties": {"type": {"type": "string", "const": target_type}}
                    }
                },
            }
            # validator_network[field] = link_validator
        if validator_network:
            type_schema["validate"]["network"] = validator_network

        schemas.append(type_schema)

    # Write schema_definitions to JSON file in confdir
    schemas_output_path = Path(app.confdir) / "schemas.json"
    with open(schemas_output_path, "w", encoding="utf-8") as f:
        json.dump(schema_definitions, f, indent=2, ensure_ascii=False)

    config.needs_schema_definitions_from_json = "schemas.json"
    # config.needs_schema_definitions = schema_definitions


def get_field_pattern_schema(field: str, pattern: str):
    if field in SN_ARRAY_FIELDS:
        return get_array_pattern_schema(pattern)
    return get_pattern_schema(pattern)


def get_pattern_schema(pattern: str):
    return {
        "type": "string",
        "pattern": pattern,
    }


def get_array_pattern_schema(pattern: str):
    return {
        "type": "array",
        "items": get_pattern_schema(pattern),
    }
