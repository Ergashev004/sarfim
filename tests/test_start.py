from bot.handlers.start import build_welcome_text


def test_welcome_uses_first_name():
    assert "<b>Akobir</b>" in build_welcome_text("Akobir")


def test_welcome_without_name_falls_back():
    assert "do'stim" in build_welcome_text(None)


def test_welcome_escapes_html_in_name():
    text = build_welcome_text("<script>")
    assert "<script>" not in text
    assert "&lt;script&gt;" in text
