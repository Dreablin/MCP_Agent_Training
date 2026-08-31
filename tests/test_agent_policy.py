from apps.agent_app.policy import PolicyDecision, PolicyEngine


def test_email_send_always_requires_confirmation() -> None:
    result = PolicyEngine().evaluate(
        {
            "name": "email_send_email",
            "id": "call-email",
            "args": {
                "recipient_email": "recipient@example.test",
                "subject": "Meetings",
                "body": "Tomorrow you have a meeting.",
            },
        },
        {},
    )

    assert result.decision is PolicyDecision.CONFIRM
    assert result.rule_id == "email.send.always_confirm"
    assert result.display_payload["details"] == {
        "recipient_email": "recipient@example.test",
        "subject": "Meetings",
        "body": "Tomorrow you have a meeting.",
    }


def test_other_tools_are_allowed_by_default() -> None:
    result = PolicyEngine().evaluate(
        {"name": "calendar_create_calendar_event", "id": "call-calendar", "args": {}},
        {"thread_id": "thread-1"},
    )

    assert result.decision is PolicyDecision.ALLOW
    assert result.rule_id == "default.allow"


def test_rejected_email_send_is_denied_in_current_request() -> None:
    result = PolicyEngine().evaluate(
        {"name": "email_send_email", "id": "call-email", "args": {}},
        {"rejected_tool_names": ["email_send_email"]},
    )

    assert result.decision is PolicyDecision.DENY
    assert result.rule_id == "email.send.rejected_in_current_request"
    assert "Do not retry" in result.reason
