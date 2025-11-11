from sphinx.config import Config

from src.extensions.score_metamodel.yaml_parser import MetaModelData

SN_ARRAY_FIELDS = {
    "tags",
    "sections",
}


def write_sn_schemas(config: Config, metamodel: MetaModelData) -> None:
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
            validator_local["required"].append(field)
            validator_local["properties"][field] = get_field_pattern_schema(
                field, pattern
            )
        for field, pattern in optional_fields.items():
            validator_local["properties"][field] = get_field_pattern_schema(
                field, pattern
            )
        for field, pattern in mandatory_links.items():
            validator_local["required"].append(field)
            if pattern.startswith("^"):
                validator_local["properties"][field] = get_array_pattern_schema(pattern)
        for field, pattern in optional_links.items():
            if pattern.startswith("^"):
                validator_local["properties"][field] = get_array_pattern_schema(pattern)

        type_schema["validate"]["local"] = validator_local

        validator_network = {}
        for field, pattern in mandatory_links.items():
            if not pattern.startswith("^"):
                link_validator = {
                    "contains": {
                        "local": {
                            "properties": {"type": {"type": "string", "const": pattern}}
                        }
                    },
                    "minContains": 1,
                }
                validator_network[field] = link_validator
        for field, pattern in optional_links.items():
            if not pattern.startswith("^"):
                link_validator = {
                    "contains": {
                        "local": {
                            "properties": {"type": {"type": "string", "const": pattern}}
                        },
                    },
                    "minContains": 0,
                }
                validator_network[field] = link_validator
        if validator_network:
            type_schema["validate"]["network"] = validator_network

        schemas.append(type_schema)

    config.needs_schema_definitions = schema_definitions


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
