from secretary_ai.core.config import Settings
from secretary_ai.services.live_templates import LiveTemplateMatcher


def test_template_matcher_uses_default_templates(tmp_path) -> None:
    template_path = tmp_path / "templates.json"
    matcher = LiveTemplateMatcher(Settings(agent_live_template_path=str(template_path)))

    reply = matcher.match("hello there")
    assert reply is not None
    assert "hi" in reply.lower() or "here" in reply.lower()


def test_template_matcher_returns_none_when_no_keyword(tmp_path) -> None:
    template_path = tmp_path / "templates.json"
    matcher = LiveTemplateMatcher(Settings(agent_live_template_path=str(template_path)))

    reply = matcher.match("quantum entanglement theorem")
    assert reply is None


def test_template_matcher_disabled_flag(tmp_path) -> None:
    template_path = tmp_path / "templates.json"
    matcher = LiveTemplateMatcher(
        Settings(agent_live_template_path=str(template_path), agent_live_template_enabled=False)
    )

    reply = matcher.match("hello")
    assert reply is None
