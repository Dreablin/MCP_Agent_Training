from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class PolicyDecision(StrEnum):
    ALLOW = "allow"
    CONFIRM = "confirm"
    DENY = "deny"


@dataclass(frozen=True)
class PolicyResult:
    decision: PolicyDecision
    rule_id: str
    reason: str
    display_payload: dict[str, Any]


class PolicyEngine:
    """Evaluate a planned tool call without invoking the model or a tool."""

    def evaluate(
        self,
        tool_call: Mapping[str, Any],
        state: Mapping[str, Any],
    ) -> PolicyResult:
        tool_name = str(tool_call.get("name", ""))
        rejected_tool_names = state.get("rejected_tool_names", [])
        if (
            tool_name == "email_send_email"
            and isinstance(rejected_tool_names, list)
            and tool_name in rejected_tool_names
        ):
            return PolicyResult(
                decision=PolicyDecision.DENY,
                rule_id="email.send.rejected_in_current_request",
                reason=(
                    "The user already rejected email sending in the current request. "
                    "Do not retry it until the user sends a new request."
                ),
                display_payload={},
            )
        if tool_name == "email_send_email":
            return PolicyResult(
                decision=PolicyDecision.CONFIRM,
                rule_id="email.send.always_confirm",
                reason="email_send_email always requires approval.",
                display_payload=email_approval_payload(tool_call),
            )
        return PolicyResult(
            decision=PolicyDecision.ALLOW,
            rule_id="default.allow",
            reason="The current tool policy allows this tool call.",
            display_payload={},
        )


def email_approval_payload(tool_call: Mapping[str, Any]) -> dict[str, Any]:
    raw_args = tool_call.get("args", {})
    args = raw_args if isinstance(raw_args, Mapping) else {}
    recipient = string_argument(args, "recipient_email")
    subject = string_argument(args, "subject")
    body = string_argument(args, "body")
    return {
        "kind": "tool_approval",
        "question": "Approve sending this email?",
        "reason": "Email sending always requires your approval.",
        "action": "send_email",
        "tool_name": str(tool_call.get("name", "email_send_email")),
        "tool_call_id": str(tool_call.get("id", "")),
        "details": {
            "recipient_email": recipient,
            "subject": subject,
            "body": body,
        },
        "options": [
            {"id": "approve", "label": "Approve"},
            {"id": "reject", "label": "Cancel"},
        ],
    }


def string_argument(args: Mapping[str, Any], name: str) -> str:
    value = args.get(name, "")
    return value if isinstance(value, str) else str(value)
