#!/usr/bin/env python3
"""Generate the unsigned Clipboard Snap Apple Shortcut plist."""

from __future__ import annotations

import argparse
import json
import plistlib
import re
import sys
import tomllib
import uuid
from pathlib import Path
from typing import Any


PLACEHOLDER = "\ufffc"
NAMESPACE = uuid.UUID("bbf3ad85-7955-4d33-8804-3b673a5fbd9e")
DEFAULT_ENDPOINT = "https://DATABASE-ORG.turso.io/v2/pipeline"
TOKEN_PLACEHOLDER = "PASTE_DATABASE_TOKEN_HERE"
SQL = "INSERT INTO clips (text, source) VALUES (CAST(? AS TEXT), 'ios-shortcut')"
DEFAULT_PATTERNS_FILE = Path(__file__).resolve().parents[3] / "config.toml"
BLOCKED_MESSAGE = (
    "Blocked: this text matched a sensitive-data pattern (config.toml) "
    "and was not sent to Turso."
)


def load_sensitive_pattern(path: Path) -> str:
    """Join config.toml's [[patterns]] regexes into one ICU alternation."""
    with path.open("rb") as config_file:
        config = tomllib.load(config_file)
    patterns = config.get("patterns", [])
    if not patterns:
        raise SystemExit(f"no [[patterns]] entries found in {path}")
    # `[[:space:]]`/`[^[:space:]]` are POSIX-class syntax written for
    # grep -E; ICU supports it too, but `\s`/`\S` are the unambiguous forms
    # on the Shortcuts side.
    def to_icu(regex: str) -> str:
        return regex.replace("[^[:space:]]", r"\S").replace("[[:space:]]", r"\s")

    return "|".join(f"(?:{to_icu(entry['regex'])})" for entry in patterns)


def stable_uuid(label: str) -> str:
    return str(uuid.uuid5(NAMESPACE, label)).upper()


def action(identifier: str, parameters: dict[str, Any]) -> dict[str, Any]:
    return {
        "WFWorkflowActionIdentifier": identifier,
        "WFWorkflowActionParameters": parameters,
    }


def output_reference(action_uuid: str, output_name: str) -> dict[str, Any]:
    return {
        "OutputName": output_name,
        "OutputUUID": action_uuid,
        "Type": "ActionOutput",
    }


def token_attachment(action_uuid: str, output_name: str) -> dict[str, Any]:
    return {
        "Value": output_reference(action_uuid, output_name),
        "WFSerializationType": "WFTextTokenAttachment",
    }


def token_string(
    value: str,
    attachments: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "Value": {
            "attachmentsByRange": attachments or {},
            "string": value,
        },
        "WFSerializationType": "WFTextTokenString",
    }


def output_token_string(
    action_uuid: str,
    output_name: str,
    *,
    prefix: str = "",
    suffix: str = "",
) -> dict[str, Any]:
    value = f"{prefix}{PLACEHOLDER}{suffix}"
    key = f"{{{len(prefix)}, 1}}"
    return token_string(value, {key: output_reference(action_uuid, output_name)})


def extension_input_token_string() -> dict[str, Any]:
    return token_string(
        PLACEHOLDER,
        {"{0, 1}": {"Type": "ExtensionInput"}},
    )


def dictionary_value(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "Value": {"WFDictionaryFieldValueItems": items},
        "WFSerializationType": "WFDictionaryFieldValue",
    }


def text_field(
    key: str,
    value: str | dict[str, Any],
) -> dict[str, Any]:
    return {
        "WFItemType": 0,
        "WFKey": token_string(key),
        "WFValue": token_string(value) if isinstance(value, str) else value,
    }


def dictionary_field(key: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "WFItemType": 3,
        "WFKey": token_string(key),
        "WFValue": {"Value": dictionary_value(items)},
    }


def array_field(key: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "WFItemType": 2,
        "WFKey": token_string(key),
        "WFValue": {
            "Value": items,
            "WFSerializationType": "WFArrayParameterState",
        },
    }


def dictionary_array_item(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "WFItemType": 3,
        "WFValue": {"Value": dictionary_value(items)},
    }


def header_values(token_uuid: str, token: str) -> dict[str, Any]:
    authorization: str | dict[str, Any]
    if token == TOKEN_PLACEHOLDER:
        authorization = output_token_string(token_uuid, "Text", prefix="Bearer ")
    else:
        authorization = f"Bearer {token}"
    return dictionary_value(
        [
            text_field("Authorization", authorization),
            text_field("Content-Type", "application/json"),
        ]
    )


def pipeline_json_text(base64_uuid: str) -> dict[str, Any]:
    sentinel = "__SHORTCUT_BASE64__"
    payload = {
        "requests": [
            {
                "type": "execute",
                "stmt": {
                    "sql": SQL,
                    "args": [{"type": "blob", "base64": sentinel}],
                },
            },
            {"type": "close"},
        ]
    }
    serialized = json.dumps(payload, ensure_ascii=True, separators=(",", ":"))
    placeholder_index = serialized.index(sentinel)
    serialized = serialized.replace(sentinel, PLACEHOLDER, 1)
    return token_string(
        serialized,
        {
            f"{{{placeholder_index}, 1}}": output_reference(
                base64_uuid,
                "Encoded text",
            )
        },
    )


def variable_condition_input(action_uuid: str, output_name: str) -> dict[str, Any]:
    return {
        "Type": "Variable",
        "Variable": token_attachment(action_uuid, output_name),
    }


def build_shortcut(
    name: str,
    endpoint: str = DEFAULT_ENDPOINT,
    token: str = TOKEN_PLACEHOLDER,
    patterns_file: Path = DEFAULT_PATTERNS_FILE,
) -> dict[str, Any]:
    sensitive_pattern = load_sensitive_pattern(patterns_file)
    credential_note = (
        "The Turso endpoint and insert-only database token are requested "
        "during import. Keep the configured shortcut private."
        if token == TOKEN_PLACEHOLDER
        else "The Turso endpoint and insert-only database token are embedded. "
        "Keep this configured shortcut private."
    )
    endpoint_uuid = stable_uuid("endpoint-text")
    token_uuid = stable_uuid("token-text")
    input_uuid = stable_uuid("shortcut-input-text")
    base64_uuid = stable_uuid("base64-input")
    body_uuid = stable_uuid("request-json")
    request_uuid = stable_uuid("turso-request")
    dictionary_uuid = stable_uuid("response-dictionary")
    results_uuid = stable_uuid("response-results")
    first_result_uuid = stable_uuid("first-result")
    result_type_uuid = stable_uuid("result-type")
    result_type_text_uuid = stable_uuid("result-type-text")
    split_text_uuid = stable_uuid("split-text-lines")
    first_line_uuid = stable_uuid("first-text-line")
    input_condition_group_uuid = stable_uuid("input-condition")
    condition_group_uuid = stable_uuid("result-condition")
    match_text_uuid = stable_uuid("sensitive-match-text")
    sensitive_condition_group_uuid = stable_uuid("sensitive-condition")

    actions = [
        action(
            "is.workflow.actions.comment",
            {
                "WFCommentActionText": (
                    "Save selected text from the Share Sheet, or copied text "
                    "from the clipboard when run directly, to Turso."
                )
            },
        ),
        action(
            "is.workflow.actions.comment",
            {
                "WFCommentActionText": (
                    "Shortcuts generated by Shortcuts Playground. May contain mistakes. "
                    "Always check the shortcut's actions first.\n\n"
                    f"{credential_note}"
                )
            },
        ),
        action(
            "is.workflow.actions.gettext",
            {
                "UUID": endpoint_uuid,
                "CustomOutputName": "Turso pipeline URL",
                "WFTextActionText": endpoint,
            },
        ),
        action(
            "is.workflow.actions.gettext",
            {
                "UUID": token_uuid,
                "CustomOutputName": "Turso database token",
                "WFTextActionText": token,
            },
        ),
        action(
            "is.workflow.actions.gettext",
            {
                "UUID": input_uuid,
                "CustomOutputName": "Text to save",
                "WFTextActionText": extension_input_token_string(),
            },
        ),
        action(
            "is.workflow.actions.comment",
            {
                "WFCommentActionText": (
                    "Continue only when there is text to save.\n"
                    "- Input uses selected text or the clipboard\n"
                    "- Has Any Value continues to the Turso request"
                )
            },
        ),
        action(
            "is.workflow.actions.conditional",
            {
                "GroupingIdentifier": input_condition_group_uuid,
                "WFCondition": 100,
                "WFControlFlowMode": 0,
                "WFInput": variable_condition_input(input_uuid, "Text"),
            },
        ),
        action(
            "is.workflow.actions.comment",
            {
                "WFCommentActionText": (
                    "Block sending if the text matches a curated sensitive-data "
                    "pattern from config.toml (credentials, cookies, hospital "
                    "URLs, card numbers, wallet seed phrases, ...)."
                )
            },
        ),
        action(
            "is.workflow.actions.text.match",
            {
                "UUID": match_text_uuid,
                "CustomOutputName": "Text Matches",
                "WFMatchTextCaseSensitive": False,
                "WFMatchTextPattern": token_string(sensitive_pattern),
                "text": token_attachment(input_uuid, "Text"),
            },
        ),
        action(
            "is.workflow.actions.conditional",
            {
                "GroupingIdentifier": sensitive_condition_group_uuid,
                "WFCondition": 100,
                "WFControlFlowMode": 0,
                "WFInput": variable_condition_input(match_text_uuid, "Text Matches"),
            },
        ),
        action(
            "is.workflow.actions.showresult",
            {"Text": token_string(BLOCKED_MESSAGE)},
        ),
        action(
            "is.workflow.actions.exit",
            {},
        ),
        action(
            "is.workflow.actions.conditional",
            {
                "GroupingIdentifier": sensitive_condition_group_uuid,
                "WFControlFlowMode": 1,
            },
        ),
        action(
            "is.workflow.actions.conditional",
            {
                "GroupingIdentifier": sensitive_condition_group_uuid,
                "UUID": stable_uuid("end-sensitive-condition"),
                "WFControlFlowMode": 2,
            },
        ),
        action(
            "is.workflow.actions.comment",
            {
                "WFCommentActionText": (
                    "Insert the text with a bound SQL parameter. Turso creates "
                    "the record ID and UTC timestamp."
                )
            },
        ),
        action(
            "is.workflow.actions.base64encode",
            {
                "UUID": base64_uuid,
                "CustomOutputName": "Encoded text",
                "WFBase64LineBreakMode": "None",
                "WFEncodeMode": "Encode",
                "WFInput": token_attachment(input_uuid, "Text"),
            },
        ),
        action(
            "is.workflow.actions.gettext",
            {
                "UUID": body_uuid,
                "CustomOutputName": "Request JSON",
                "WFTextActionText": pipeline_json_text(base64_uuid),
            },
        ),
        action(
            "is.workflow.actions.downloadurl",
            {
                "Advanced": True,
                "ShowHeaders": False,
                "UUID": request_uuid,
                "WFFormValues": dictionary_value([]),
                "WFHTTPBodyType": "File",
                "WFHTTPHeaders": header_values(token_uuid, token),
                "WFHTTPMethod": "POST",
                "WFRequestVariable": token_attachment(body_uuid, "Request JSON"),
                "WFURL": (
                    output_token_string(endpoint_uuid, "Text")
                    if token == TOKEN_PLACEHOLDER
                    else token_string(endpoint)
                ),
            },
        ),
        action(
            "is.workflow.actions.detect.dictionary",
            {
                "UUID": dictionary_uuid,
                "WFInput": token_attachment(request_uuid, "Contents of URL"),
            },
        ),
        action(
            "is.workflow.actions.getvalueforkey",
            {
                "UUID": results_uuid,
                "WFDictionaryKey": "results",
                "WFGetDictionaryValueType": "Value",
                "WFInput": token_attachment(dictionary_uuid, "Dictionary"),
            },
        ),
        action(
            "is.workflow.actions.getitemfromlist",
            {
                "UUID": first_result_uuid,
                "WFInput": token_attachment(results_uuid, "Dictionary Value"),
                "WFItemSpecifier": "First Item",
            },
        ),
        action(
            "is.workflow.actions.getvalueforkey",
            {
                "UUID": result_type_uuid,
                "WFDictionaryKey": "type",
                "WFGetDictionaryValueType": "Value",
                "WFInput": token_attachment(first_result_uuid, "Item from List"),
            },
        ),
        action(
            "is.workflow.actions.gettext",
            {
                "UUID": result_type_text_uuid,
                "CustomOutputName": "Turso result type",
                "WFTextActionText": output_token_string(
                    result_type_uuid,
                    "Dictionary Value",
                ),
            },
        ),
        action(
            "is.workflow.actions.comment",
            {
                "WFCommentActionText": (
                    "Check Turso's first pipeline result.\n"
                    "- Input uses the result type returned by Turso\n"
                    "- 'ok' means the INSERT completed"
                )
            },
        ),
        action(
            "is.workflow.actions.conditional",
            {
                "GroupingIdentifier": condition_group_uuid,
                "WFCondition": 4,
                "WFConditionalActionString": "ok",
                "WFControlFlowMode": 0,
                "WFInput": variable_condition_input(
                    result_type_text_uuid,
                    "Text",
                ),
            },
        ),
        action(
            "is.workflow.actions.text.split",
            {
                "Show-text": True,
                "UUID": split_text_uuid,
                "CustomOutputName": "Text lines",
                "WFTextSeparator": "New Lines",
                "text": token_attachment(input_uuid, "Text"),
            },
        ),
        action(
            "is.workflow.actions.getitemfromlist",
            {
                "UUID": first_line_uuid,
                "CustomOutputName": "First line",
                "WFInput": token_attachment(split_text_uuid, "Text lines"),
                "WFItemSpecifier": "First Item",
            },
        ),
        action(
            "is.workflow.actions.notification",
            {
                "UUID": stable_uuid("success-notification"),
                "WFNotificationActionBody": output_token_string(
                    first_line_uuid,
                    "First line",
                    suffix="...",
                ),
                "WFNotificationActionTitle": "Text saved to Turso.",
            },
        ),
        action(
            "is.workflow.actions.conditional",
            {
                "GroupingIdentifier": condition_group_uuid,
                "WFControlFlowMode": 1,
            },
        ),
        action(
            "is.workflow.actions.showresult",
            {
                "Text": output_token_string(
                    first_result_uuid,
                    "Item from List",
                    prefix="Turso rejected the insert.\n\n",
                )
            },
        ),
        action(
            "is.workflow.actions.conditional",
            {
                "GroupingIdentifier": condition_group_uuid,
                "UUID": stable_uuid("end-result-condition"),
                "WFControlFlowMode": 2,
            },
        ),
        action(
            "is.workflow.actions.conditional",
            {
                "GroupingIdentifier": input_condition_group_uuid,
                "WFControlFlowMode": 1,
            },
        ),
        action(
            "is.workflow.actions.showresult",
            {
                "Text": token_string(
                    "Nothing to save. Select or copy some text, then run Clipboard Snap again."
                )
            },
        ),
        action(
            "is.workflow.actions.conditional",
            {
                "GroupingIdentifier": input_condition_group_uuid,
                "UUID": stable_uuid("end-input-condition"),
                "WFControlFlowMode": 2,
            },
        ),
    ]

    return {
        "WFWorkflowActions": actions,
        "WFWorkflowClientRelease": "26.2",
        "WFWorkflowClientVersion": "2602.0.1",
        "WFWorkflowHasOutputFallback": False,
        "WFWorkflowHasShortcutInputVariables": True,
        "WFWorkflowIcon": {
            "WFWorkflowIconGlyphNumber": 59714,
            "WFWorkflowIconStartColor": 431817727,
        },
        "WFWorkflowImportQuestions": [] if token != TOKEN_PLACEHOLDER else [
            {
                "ActionIndex": 2,
                "Category": "Parameter",
                "DefaultValue": endpoint,
                "ParameterKey": "WFTextActionText",
                "Text": "Turso pipeline URL (HTTP URL + /v2/pipeline)",
            },
            {
                "ActionIndex": 3,
                "Category": "Parameter",
                "DefaultValue": TOKEN_PLACEHOLDER,
                "ParameterKey": "WFTextActionText",
                "Text": "Turso database token (token only, without Bearer)",
            },
        ],
        "WFWorkflowInputContentItemClasses": [
            "WFRichTextContentItem",
            "WFStringContentItem",
        ],
        "WFWorkflowIsDisabledOnLockScreen": True,
        "WFWorkflowMinimumClientVersion": 1113,
        "WFWorkflowMinimumClientVersionString": "1113",
        "WFWorkflowName": name,
        "WFWorkflowNoInputBehavior": {
            "Name": "WFWorkflowNoInputBehaviorGetClipboard",
            "Parameters": {},
        },
        "WFWorkflowOutputContentItemClasses": [],
        "WFWorkflowTypes": ["ActionExtension"],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="Clipboard Snap")
    parser.add_argument(
        "--endpoint",
        default=DEFAULT_ENDPOINT,
        help="prefill a public https://*.turso.io/v2/pipeline endpoint",
    )
    parser.add_argument(
        "--token-stdin",
        action="store_true",
        help="embed a JWT read from stdin and omit import questions",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("dist/Clipboard Snap.xml"),
    )
    parser.add_argument(
        "--patterns-file",
        type=Path,
        default=DEFAULT_PATTERNS_FILE,
        help="config.toml providing the [[patterns]] sensitive-data regex list",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    token = TOKEN_PLACEHOLDER
    if args.token_stdin:
        token = sys.stdin.read().strip()
        if not re.fullmatch(
            r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",
            token,
        ):
            raise SystemExit("stdin does not contain one JWT-shaped database token")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("wb") as output_file:
        plistlib.dump(
            build_shortcut(args.name, args.endpoint, token, args.patterns_file),
            output_file,
            fmt=plistlib.FMT_XML,
            sort_keys=False,
        )
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
