#!/usr/bin/env python3
"""Validate Clipboard Snap's generated plist and credential contract."""

from __future__ import annotations

import argparse
import json
import plistlib
import re
import tomllib
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

# Validate against the same tracked template the public build reads. The real
# config.toml is git-ignored; a private build is checked against its own source.
_REPO_ROOT = Path(__file__).resolve().parents[3]
PATTERNS_FILE = _REPO_ROOT / "config.toml.example"
if not PATTERNS_FILE.is_file():
    PATTERNS_FILE = _REPO_ROOT / "config.toml"


EXPECTED_ACTIONS = [
    "is.workflow.actions.comment",
    "is.workflow.actions.comment",
    "is.workflow.actions.gettext",
    "is.workflow.actions.gettext",
    "is.workflow.actions.gettext",
    "is.workflow.actions.comment",
    "is.workflow.actions.conditional",
    "is.workflow.actions.comment",
    "is.workflow.actions.text.match",
    "is.workflow.actions.conditional",
    "is.workflow.actions.showresult",
    "is.workflow.actions.exit",
    "is.workflow.actions.conditional",
    "is.workflow.actions.conditional",
    "is.workflow.actions.comment",
    "is.workflow.actions.text.match",
    "is.workflow.actions.count",
    "is.workflow.actions.conditional",
    "is.workflow.actions.showresult",
    "is.workflow.actions.exit",
    "is.workflow.actions.conditional",
    "is.workflow.actions.conditional",
    "is.workflow.actions.comment",
    "is.workflow.actions.base64encode",
    "is.workflow.actions.gettext",
    "is.workflow.actions.downloadurl",
    "is.workflow.actions.detect.dictionary",
    "is.workflow.actions.getvalueforkey",
    "is.workflow.actions.getitemfromlist",
    "is.workflow.actions.getvalueforkey",
    "is.workflow.actions.gettext",
    "is.workflow.actions.comment",
    "is.workflow.actions.conditional",
    "is.workflow.actions.text.split",
    "is.workflow.actions.getitemfromlist",
    "is.workflow.actions.notification",
    "is.workflow.actions.conditional",
    "is.workflow.actions.showresult",
    "is.workflow.actions.conditional",
    "is.workflow.actions.conditional",
    "is.workflow.actions.showresult",
    "is.workflow.actions.conditional",
]
SQL = "INSERT INTO clips (text, source) VALUES (CAST(? AS TEXT), 'ios-shortcut')"
ENDPOINT_PLACEHOLDER = "https://DATABASE-ORG.turso.io/v2/pipeline"
TOKEN_PLACEHOLDER = "PASTE_DATABASE_TOKEN_HERE"
PLACEHOLDER = "\ufffc"
BLOCKED_MESSAGE = (
    "Blocked: this text matched a sensitive-data pattern (config.toml) "
    "and was not sent to Turso."
)


def fail(message: str) -> None:
    raise ValueError(message)


def valid_endpoint(value: str) -> bool:
    if value == ENDPOINT_PLACEHOLDER:
        return True
    parsed = urlsplit(value)
    return (
        parsed.scheme == "https"
        and parsed.hostname is not None
        and parsed.hostname.endswith(".turso.io")
        and parsed.path == "/v2/pipeline"
        and not parsed.username
        and not parsed.password
        and not parsed.query
        and not parsed.fragment
    )


def walk_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [item for child in value.values() for item in walk_strings(child)]
    if isinstance(value, list):
        return [item for child in value for item in walk_strings(child)]
    return []


def decode_token_string(value: dict[str, Any]) -> str:
    state = value["Value"]
    decoded = state["string"]
    for _ in state.get("attachmentsByRange", {}):
        decoded = decoded.replace(PLACEHOLDER, "<dynamic>", 1)
    return decoded


def decode_dictionary(value: dict[str, Any]) -> dict[str, Any]:
    items = value["Value"]["WFDictionaryFieldValueItems"]
    decoded: dict[str, Any] = {}
    for item in items:
        key = decode_token_string(item["WFKey"])
        item_type = item["WFItemType"]
        if item_type == 0:
            decoded[key] = decode_token_string(item["WFValue"])
        elif item_type == 2:
            decoded[key] = [decode_array_item(child) for child in item["WFValue"]["Value"]]
        elif item_type == 3:
            decoded[key] = decode_dictionary(item["WFValue"]["Value"])
        else:
            fail(f"unsupported dictionary item type: {item_type}")
    return decoded


def decode_array_item(item: dict[str, Any]) -> Any:
    item_type = item["WFItemType"]
    if item_type == 0:
        return decode_token_string(item["WFValue"])
    if item_type == 3:
        return decode_dictionary(item["WFValue"]["Value"])
    fail(f"unsupported array item type: {item_type}")


def validate(
    path: Path,
    *,
    allow_configured_token: bool = False,
) -> None:
    with path.open("rb") as plist_file:
        workflow = plistlib.load(plist_file)

    actions = workflow.get("WFWorkflowActions", [])
    identifiers = [action.get("WFWorkflowActionIdentifier") for action in actions]
    if identifiers != EXPECTED_ACTIONS:
        fail("action sequence differs from the validated Clipboard Snap contract")

    endpoint = actions[2]["WFWorkflowActionParameters"]["WFTextActionText"]
    token = actions[3]["WFWorkflowActionParameters"]["WFTextActionText"]
    questions = workflow.get("WFWorkflowImportQuestions")
    if not valid_endpoint(endpoint):
        fail("endpoint must be the placeholder or an https://*.turso.io/v2/pipeline URL")
    if token == TOKEN_PLACEHOLDER:
        if not isinstance(questions, list) or len(questions) != 2:
            fail("placeholder builds require exactly two import questions")
        if [question.get("ActionIndex") for question in questions] != [2, 3]:
            fail("import questions must target endpoint and token Text actions")
        if questions[0].get("DefaultValue") != endpoint:
            fail("endpoint import question must match the endpoint Text action")
    else:
        if not allow_configured_token:
            fail("generated plist contains a configured database token")
        if not re.fullmatch(
            r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",
            token,
        ):
            fail("configured database token is not JWT-shaped")
        if questions not in (None, []):
            fail("configured builds must not expose setup questions")

    if workflow.get("WFWorkflowNoInputBehavior", {}).get("Name") != (
        "WFWorkflowNoInputBehaviorGetClipboard"
    ):
        fail("no-input behavior must read the clipboard")
    if workflow.get("WFWorkflowTypes") != ["ActionExtension"]:
        fail("workflow must be available in the Share Sheet")
    if workflow.get("WFWorkflowIsDisabledOnLockScreen") is not True:
        fail("workflow must be disabled on the lock screen")

    match_action = actions[8]["WFWorkflowActionParameters"]
    if match_action.get("WFMatchTextCaseSensitive") is not False:
        fail("sensitive-data match must be case-insensitive")
    if not decode_token_string(match_action.get("WFMatchTextPattern", {})):
        fail("sensitive-data match pattern must not be empty")
    if match_action.get("text") != {
        "Value": {
            "OutputName": "Text",
            "OutputUUID": actions[4]["WFWorkflowActionParameters"]["UUID"],
            "Type": "ActionOutput",
        },
        "WFSerializationType": "WFTextTokenAttachment",
    }:
        fail("sensitive-data match must scan the saved text")

    sensitive_condition = actions[9]["WFWorkflowActionParameters"]
    if sensitive_condition.get("WFCondition") != 100:
        fail("sensitive-data check must use Has Any Value")
    if sensitive_condition.get("WFInput", {}).get("Variable", {}).get(
        "Value", {}
    ).get("OutputUUID") != actions[8]["WFWorkflowActionParameters"]["UUID"]:
        fail("sensitive-data check must read the Match Text output")

    if decode_token_string(
        actions[10]["WFWorkflowActionParameters"]["Text"]
    ) != BLOCKED_MESSAGE:
        fail("blocked-send message differs from the contract")
    if actions[11]["WFWorkflowActionParameters"] != {}:
        fail("Exit Shortcut after a sensitive match must take no parameters")

    with PATTERNS_FILE.open("rb") as config_file:
        count_patterns = tomllib.load(config_file).get("count_patterns", [])
    if len(count_patterns) != 1:
        fail(
            "this validator's fixed action indices assume exactly one "
            "[[count_patterns]] entry in config.toml; update EXPECTED_ACTIONS "
            "and the indices below if that count changed"
        )
    count_entry = count_patterns[0]

    count_match_action = actions[15]["WFWorkflowActionParameters"]
    if count_match_action.get("WFMatchTextCaseSensitive") is not False:
        fail("bulk-count match must be case-insensitive")
    if decode_token_string(
        count_match_action.get("WFMatchTextPattern", {})
    ) != count_entry["icu_regex"]:
        fail("bulk-count match pattern differs from config.toml's icu_regex")
    if count_match_action.get("text") != {
        "Value": {
            "OutputName": "Text",
            "OutputUUID": actions[4]["WFWorkflowActionParameters"]["UUID"],
            "Type": "ActionOutput",
        },
        "WFSerializationType": "WFTextTokenAttachment",
    }:
        fail("bulk-count match must scan the saved text")

    count_action = actions[16]["WFWorkflowActionParameters"]
    if count_action.get("WFCountType") != "Items":
        fail("bulk-count action must count Items")
    if count_action.get("Input", {}).get("Value", {}).get(
        "OutputUUID"
    ) != count_match_action["UUID"]:
        fail("bulk-count action must count the Match Text output")

    count_condition = actions[17]["WFWorkflowActionParameters"]
    if count_condition.get("WFCondition") != 3:
        fail("bulk-count check must use 'is greater than or equal to'")
    if count_condition.get("WFNumberValue") != str(count_entry["min_count"]):
        fail("bulk-count threshold differs from config.toml's min_count")
    if count_condition.get("WFInput", {}).get("Variable", {}).get(
        "Value", {}
    ).get("OutputUUID") != count_action["UUID"]:
        fail("bulk-count check must read the Count action's output")

    if not decode_token_string(actions[18]["WFWorkflowActionParameters"]["Text"]):
        fail("bulk-count blocked-send message must not be empty")
    if actions[19]["WFWorkflowActionParameters"] != {}:
        fail("Exit Shortcut after a bulk-count match must take no parameters")

    request_action = next(
        action
        for action in actions
        if action["WFWorkflowActionIdentifier"] == "is.workflow.actions.downloadurl"
    )
    request = request_action["WFWorkflowActionParameters"]
    if request.get("WFHTTPMethod") != "POST":
        fail("Turso request must use POST")
    if request.get("WFHTTPBodyType") != "File":
        fail("Turso request must send the JSON Text action as a file body")
    if decode_dictionary(request.get("WFFormValues", {})) != {}:
        fail("file-body request must include empty form values")
    request_variable = request["WFRequestVariable"]
    if request_variable.get("WFSerializationType") != "WFTextTokenAttachment":
        fail("request body must directly attach the JSON Text action output")
    if request_variable.get("Value", {}).get("OutputName") != "Request JSON":
        fail("request body must reference the JSON Text action")

    base64_action = next(
        action
        for action in actions
        if action["WFWorkflowActionIdentifier"] == "is.workflow.actions.base64encode"
    )
    base64_parameters = base64_action["WFWorkflowActionParameters"]
    if base64_parameters.get("WFEncodeMode") != "Encode":
        fail("input must be Base64 encoded")
    if base64_parameters.get("WFBase64LineBreakMode") != "None":
        fail("Base64 output must not contain line breaks")

    body_action = actions[24]["WFWorkflowActionParameters"]
    body_text = decode_token_string(body_action["WFTextActionText"])
    try:
        payload = json.loads(body_text.replace("<dynamic>", "VHVyc28="))
    except json.JSONDecodeError as error:
        fail(f"request Text action is not valid JSON: {error}")

    expected_payload = {
        "requests": [
            {
                "type": "execute",
                "stmt": {
                    "sql": SQL,
                    "args": [{"type": "blob", "base64": "VHVyc28="}],
                },
            },
            {"type": "close"},
        ]
    }
    if payload != expected_payload:
        fail(f"Turso pipeline payload differs from contract: {payload!r}")

    headers = decode_dictionary(request["WFHTTPHeaders"])
    expected_headers = {
        "Authorization": (
            f"Bearer {token}" if allow_configured_token else "Bearer <dynamic>"
        ),
        "Content-Type": "application/json",
    }
    if headers != expected_headers:
        fail(f"HTTP headers differ from contract: {headers!r}")
    request_url = decode_token_string(request["WFURL"])
    expected_request_url = endpoint if allow_configured_token else "<dynamic>"
    if request_url != expected_request_url:
        fail("request URL differs from the configured credential mode")

    split_action = actions[33]["WFWorkflowActionParameters"]
    expected_text_input = {
        "Value": {
            "OutputName": "Text",
            "OutputUUID": actions[4]["WFWorkflowActionParameters"]["UUID"],
            "Type": "ActionOutput",
        },
        "WFSerializationType": "WFTextTokenAttachment",
    }
    if split_action.get("WFTextSeparator") != "New Lines":
        fail("notification preview must split the saved text by new lines")
    if split_action.get("text") != expected_text_input:
        fail("Split Text must use the saved text as its explicit input")
    if "WFInput" in split_action:
        fail("Split Text must not include the legacy WFInput parameter")

    first_line_action = actions[34]["WFWorkflowActionParameters"]
    if first_line_action.get("WFItemSpecifier") != "First Item":
        fail("notification preview must select the first text line")
    if first_line_action.get("WFInput", {}).get("Value", {}).get(
        "OutputUUID"
    ) != split_action.get("UUID"):
        fail("first-line action must use the Split Text output")

    notification = actions[35]["WFWorkflowActionParameters"]
    if notification.get("WFNotificationActionTitle") != "Text saved to Turso.":
        fail("success notification title differs from the contract")
    if decode_token_string(notification["WFNotificationActionBody"]) != "<dynamic>...":
        fail("success notification body must preview the first line")
    preview_reference = next(
        iter(
            notification["WFNotificationActionBody"]["Value"][
                "attachmentsByRange"
            ].values()
        )
    )
    if preview_reference != {
        "OutputName": "First line",
        "OutputUUID": first_line_action["UUID"],
        "Type": "ActionOutput",
    }:
        fail("success notification body must reference the first-line action")

    strings = walk_strings(workflow)
    if not any(SQL in value for value in strings):
        fail("parameterized INSERT statement is missing")
    possible_jwts = [
        value
        for value in strings
        if re.fullmatch(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", value)
    ]
    if possible_jwts and not allow_configured_token:
        fail("possible JWT found in generated artifact")
    if allow_configured_token and possible_jwts != [token]:
        fail("configured build must contain exactly its database token")

    credential_mode = "configured token" if allow_configured_token else "two import questions"
    print(
        f"OK: {path} has {len(actions)} actions, {credential_mode}, "
        "the exact parameterized Turso payload, and no JWT-shaped values"
        if not allow_configured_token
        else f"OK: {path} has {len(actions)} actions, {credential_mode}, "
        "and the exact parameterized Turso payload"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("shortcut", type=Path)
    parser.add_argument("--allow-configured-token", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    validate(
        args.shortcut,
        allow_configured_token=args.allow_configured_token,
    )


if __name__ == "__main__":
    main()
