"""Offline visual scope, readable blue accents and unmodified company artwork."""
from pathlib import Path
import hashlib
from types import SimpleNamespace


def test_offline_palette_is_blue_without_changing_online_defaults(monkeypatch):
    import tkinter as tk
    from desktop.theme import color
    monkeypatch.setattr(tk, '_default_root', SimpleNamespace(offline=True))
    assert color('primary') == ('#315E8E', '#A8CFF0')
    monkeypatch.setattr(tk, '_default_root', SimpleNamespace(offline=False))
    assert color('primary') == ('#0F766E', '#2DD4BF')


def test_official_logo_is_shared_unchanged_between_clients():
    windows = Path('desktop/assets/basic_logo.jpg')
    android = Path('mobile/assets/basic_logo.jpg')
    assert windows.is_file() and android.is_file()
    assert windows.read_bytes() == android.read_bytes()
    assert hashlib.sha256(windows.read_bytes()).hexdigest() == '432417eb95db3199ec1068cdacc0173680ac24e2664c622fda54b82129c53eb4'
    from PIL import Image
    with Image.open(windows) as image:
        assert image.size == (957, 250)


def test_offline_text_and_focus_contrast(monkeypatch):
    import tkinter as tk
    from desktop.theme import color
    monkeypatch.setattr(tk, '_default_root', SimpleNamespace(offline=True))

    def luminance(hex_value):
        rgb = [int(hex_value[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [c / 12.92 if c <= .04045 else ((c + .055) / 1.055) ** 2.4 for c in rgb]
        return sum(c * weight for c, weight in zip(linear, (.2126, .7152, .0722)))

    for mode in (0, 1):
        for foreground, background, minimum in [('on_primary', 'primary', 4.5),
                                                ('text', 'bg', 4.5), ('focus', 'surface', 3)]:
            first, second = sorted([luminance(color(foreground)[mode]), luminance(color(background)[mode])])
            assert (second + .05) / (first + .05) >= minimum
