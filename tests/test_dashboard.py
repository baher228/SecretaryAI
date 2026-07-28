from html.parser import HTMLParser

from secretary_ai.ui.dashboard import DASHBOARD_HTML


class _DashboardParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.controls: list[dict[str, str | None]] = []
        self.label_targets: set[str] = set()
        self.blank_links: list[dict[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag in {"input", "select", "textarea"}:
            self.controls.append(values)
        elif tag == "label" and values.get("for"):
            self.label_targets.add(str(values["for"]))
        elif tag == "a" and values.get("target") == "_blank":
            self.blank_links.append(values)


def test_dashboard_controls_are_labelled_and_external_links_are_safe() -> None:
    parser = _DashboardParser()
    parser.feed(DASHBOARD_HTML)

    assert all(
        control.get("aria-label") or control.get("id") in parser.label_targets
        for control in parser.controls
    )
    assert all("noopener" in str(link.get("rel") or "") for link in parser.blank_links)


def test_dashboard_does_not_inline_untrusted_action_ids() -> None:
    assert 'onclick="deleteContact(' not in DASHBOARD_HTML
    assert 'onclick="cancelReminder(' not in DASHBOARD_HTML
    assert 'data-caller-id="${esc(c.caller_id)}"' in DASHBOARD_HTML
    assert 'data-event-id="${esc(rem.event_id)}"' in DASHBOARD_HTML
