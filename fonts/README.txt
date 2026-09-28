# ============================================================
#  ШРИФТЫ ДЛЯ ГЕНЕРАЦИИ ИЗОБРАЖЕНИЙ
# ============================================================
#
#  Бот ищет шрифты в ЭТОЙ папке (fonts/).
#  Если шрифт здесь не найден, используются системные:
#    Windows — C:\Windows\Fonts (Segoe UI, Arial, Verdana)
#    Linux   — /usr/share/fonts (DejaVu Sans, Noto Sans)
#    macOS   — /System/Library/Fonts
#
#  ВАЖНО: кириллица (русский язык) обязательна!
#  Шрифты без кириллицы будут пропущены автоматически.
#
# ------------------------------------------------------------
#  КАК УСТАНОВИТЬ ШРИФТЫ
# ------------------------------------------------------------
#
#  1. НУЖНЫЙ (минимум):
#
#     Inter-Regular.ttf      основной шрифт (Inter / Google Fonts)
#                             https://rsms.me/inter/
#
#  2. РЕКОМЕНДУЕМЫЙ (для красивых emoji):
#
#     NotoColorEmoji.ttf    цветные эмодзи (Google Noto Emoji)
#                             https://fonts.google.com/noto/specimen/Noto+Color+Emoji
#         или
#     NotoEmoji-Regular.ttf ч/б эмодзи (легче по размеру)
#                             https://fonts.google.com/noto/specimen/Noto+Emoji
#
#  3. АЛЬТЕРНАТИВЫ ОСНОВНОГО ШРИФТА (любой один):
#
#     Roboto-Regular.ttf     https://fonts.google.com/specimen/Roboto
#     NotoSans-Regular.ttf   https://fonts.google.com/noto/specimen/Noto+Sans
#     OpenSans-Regular.ttf   https://fonts.google.com/specimen/Open+Sans
#     Montserrat-Regular.ttf  https://fonts.google.com/specimen/Montserrat
#
#  На Windows emoji обычно есть в системе:
#     C:\Windows\Fonts\seguiemj.ttf
#  На Linux доустановите:
#     sudo apt install fonts-noto-color-emoji
#     sudo apt install fonts-dejavu-core
#
# ------------------------------------------------------------
#  БЫСТРАЯ УСТАНОВКА (без скачивания руками)
# ------------------------------------------------------------
#
#  Windows (PowerShell):
#     New-Item -ItemType Directory -Force fonts
#     Invoke-WebRequest "https://github.com/rsms/inter/releases/download/v4.0/Inter-4.0.zip" -OutFile inter.zip
#     Expand-Archive inter.zip -DestinationPath inter_tmp
#     Copy-Item inter_tmp\extras\ttf\*.ttf fonts\ -Force
#     Remove-Item inter.zip, inter_tmp -Recurse -Force
#
#  Linux / VPS:
#     sudo apt install -y fonts-inter fonts-noto-color-emoji
#     cp /usr/share/fonts/truetype/inter/*.ttf fonts/ 2>/dev/null || true
#
# ------------------------------------------------------------
#  ПРОВЕРКА ЧТО ВСЁ РАБОТАЕТ
# ------------------------------------------------------------
#
#     python check.py
#
#  В отчёте будет строка вида:
#     Шрифты: {'text_font': 'Inter-Regular.ttf',
#              'emoji_font': 'NotoColorEmoji.ttf', 'emoji_color': 'да'}
#
#  Если text_font = "встроенный Pillow" — шрифты не найдены,
#  русский текст будет отображаться некорректно.
# ============================================================
