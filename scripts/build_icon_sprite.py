"""
Build app/static/icons/sprite.svg from Lucide icons (https://lucide.dev, ISC licence).

usage: python scripts/build_icon_sprite.py <path-to-unpacked-lucide-static>/package
(get it with: npm pack lucide-static && tar -xzf lucide-static-*.tgz)

Only the icons listed in ICONS are included. Add a name here, rebuild, then use it in a template
with {{ icon('name') }}. Each icon becomes <symbol id="i-<name>">.
"""
import re
import sys
from pathlib import Path

ICONS = [
    # status & social
    'skull', 'crown', 'trophy', 'medal', 'flame', 'snowflake', 'landmark', 'swords', 'sword', 'shield',
    'wand-sparkles', 'ghost', 'gift', 'lock', 'star', 'coins',
    # quests & time
    'zap', 'pencil', 'x', 'check', 'calendar', 'hourglass', 'ruler', 'alarm-clock', 'brain',
    # condition & equipment
    'tree-palm', 'battery-low', 'tag', 'moon', 'hard-hat', 'shirt', 'gem',
    # navigation & settings
    'bell', 'settings', 'power', 'globe', 'triangle-alert', 'sparkles',
]

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'app' / 'static' / 'icons' / 'sprite.svg'
LICENCE_OUT = ROOT / 'app' / 'static' / 'icons' / 'LUCIDE_LICENSE.txt'


def main(pkg_dir):
    pkg = Path(pkg_dir)
    version = re.search(r'"version"\s*:\s*"([^"]+)"', (pkg / 'package.json').read_text()).group(1)
    symbols = []
    for name in ICONS:
        svg = (pkg / 'icons' / f'{name}.svg').read_text()
        body = re.search(r'<svg[^>]*>(.*)</svg>', svg, re.S).group(1)
        body = re.sub(r'\s+', ' ', re.sub(r'<!--.*?-->', '', body, flags=re.S)).strip()
        symbols.append(f'  <symbol id="i-{name}" viewBox="0 0 24 24">{body}</symbol>')
    OUT.write_text(
        f'<!-- Icons: Lucide v{version} (https://lucide.dev), ISC licence; see LUCIDE_LICENSE.txt -->\n'
        '<svg xmlns="http://www.w3.org/2000/svg" style="display:none">\n' + '\n'.join(symbols) + '\n</svg>\n')
    LICENCE_OUT.write_text((pkg / 'LICENSE').read_text())
    print(f'wrote {OUT.relative_to(ROOT)} ({len(ICONS)} icons, {OUT.stat().st_size:,} bytes)')


if __name__ == '__main__':
    main(sys.argv[1])
