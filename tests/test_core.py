from __future__ import annotations

import asyncio
import io
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    Chat as TelegramChat,
    Message as TelegramMessage,
    ReplyKeyboardRemove,
    User as TelegramUser,
)
from PIL import Image, ImageDraw
from sqlalchemy import delete, select
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from bot import screens
from bot.config import settings
from bot.database.repositories import BroadcastRepository, UsageRepository
from bot.database.repositories.user import UserRepository
from bot.generators import AVAILABLE_STYLES, get_renderer
from bot.generators import drawing
from bot.generators.fonts import get_font_manager, is_emoji_char, split_emoji_runs
from bot.generators.text_layout import wrap_text
from bot.handlers import ai as ai_handlers
from bot.handlers import admin, create, editor, menus as menu_handlers, start
from bot.keyboards import common as common_kb
from bot.keyboards.create import style_menu
from bot.models import Base, Chat, User
from bot.schemas import ChatConfig, MediaItem, Message, MessageKind, Participant, Reaction
from bot.services.chat_service import ChatService
from bot.services.limit_service import LimitService
from bot.services.render_service import RenderService
from bot.states import Flow
from bot.utils import text_utils as TX
from bot.utils.errors import AIUnavailableError, RenderError
from bot.utils.files import is_image_bytes
from bot.services.ai_service import AIService
from bot.utils.time_utils import parse_time


class _FixedWidthFont:
    def measure(self, text: str, size: int) -> int:
        return len(text) * 10


class TextValidationTests(unittest.TestCase):
    def test_multiline_messages_preserve_paragraphs_through_json(self) -> None:
        content = "Первая строка\r\n\r\nSecond paragraph 👨‍👩‍👧‍👦\n<literal>"
        config = ChatConfig(
            participants=[Participant(name="А", side=0), Participant(name="Б", side=1)],
            messages=[Message(text=content)],
        )

        restored = ChatConfig.from_json(config.to_json())

        self.assertEqual(
            restored.messages[0].text,
            "Первая строка\n\nSecond paragraph 👨‍👩‍👧‍👦\n<literal>",
        )

    def test_newlines_are_preserved_when_clamping(self) -> None:
        self.assertEqual(TX.clean_multiline("  a \r\n b\t c  "), "a\nb c")
        self.assertEqual(TX.clamp_multiline("a\nb\nc", 4), "a\nb…")

    def test_time_and_html_input_validation(self) -> None:
        self.assertEqual(parse_time("9.05"), "09:05")
        self.assertEqual(TX.esc("<b>&\""), "&lt;b&gt;&amp;\"")

    def test_no_break_wrapping_never_exceeds_width(self) -> None:
        lines = wrap_text("label ( word", _FixedWidthFont(), 12, 60)

        self.assertTrue(lines)
        self.assertTrue(all(_FixedWidthFont().measure(line, 12) <= 60 for line in lines))

    def test_emoji_runs_keep_joiners_and_not_hyphens(self) -> None:
        self.assertFalse(is_emoji_char("-"))
        self.assertEqual(split_emoji_runs("one-two"), [("one-two", False)])
        self.assertEqual(
            split_emoji_runs("👨‍👩‍👧‍👦"),
            [("👨‍👩‍👧‍👦", True)],
        )

    def test_color_emoji_measurement_matches_raster_width(self) -> None:
        fonts = get_font_manager()
        if not fonts.emoji.available or not fonts.emoji.color:
            self.skipTest("No color emoji font is installed")

        family = "\U0001f468\u200d\U0001f469\u200d\U0001f467\u200d\U0001f466"
        rendered = fonts._emoji_image(family, 34)

        self.assertIsNotNone(rendered)
        self.assertEqual(fonts.emoji_width(family, 34), rendered.width)

    def test_read_checks_are_drawn_at_requested_x_coordinate(self) -> None:
        image = Image.new("RGBA", (200, 80), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        drawing.draw_checks(draw, 120, 20, 20, (0, 255, 0), double=True)

        bbox = image.getchannel("A").getbbox()
        self.assertIsNotNone(bbox)
        self.assertGreaterEqual(bbox[0], 120)

    def test_buffered_photo_uses_aiogram_concrete_input_file(self) -> None:
        file = screens._as_file(b"png-bytes", "test.png")

        self.assertIsInstance(file, BufferedInputFile)

    def test_upload_rejects_images_over_pixel_budget(self) -> None:
        from PIL import Image

        stream = io.BytesIO()
        Image.new("RGB", (2, 2)).save(stream, format="PNG")
        with patch("bot.utils.files.MAX_IMAGE_PIXELS", 3):
            self.assertFalse(is_image_bytes(stream.getvalue()))


class ScreenTests(unittest.IsolatedAsyncioTestCase):
    async def test_show_message_passes_inline_keyboard_to_telegram(self) -> None:
        message = TelegramMessage(
            message_id=1,
            date=datetime.now(timezone.utc),
            chat=TelegramChat(id=1, type="private"),
            text="prompt",
        )
        keyboard = common_kb.main_menu_inline()

        with patch.object(
            TelegramMessage, "answer", new_callable=AsyncMock
        ) as answer:
            await screens.show(message, "editor", keyboard)

        answer.assert_awaited_once()
        self.assertIs(answer.await_args.kwargs["reply_markup"], keyboard)


class AdminPermissionTests(unittest.TestCase):
    def test_admin_access_uses_configured_ids(self) -> None:
        with patch.object(settings, "admin_ids", [1001]):
            self.assertTrue(admin.is_admin(1001))
            self.assertFalse(admin.is_admin(1002))


class StatsCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_stats_command_dispatches_to_admin_statistics(self) -> None:
        message = SimpleNamespace(from_user=SimpleNamespace(id=1001))
        with (
            patch.object(settings, "admin_ids", [1001]),
            patch.object(admin, "send_stats", new_callable=AsyncMock) as send_stats,
        ):
            await start.cmd_stats(message)
        send_stats.assert_awaited_once_with(message)


class FSMRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancel_clears_state_and_returns_to_menu(self) -> None:
        message = SimpleNamespace(answer=AsyncMock())
        state = SimpleNamespace(clear=AsyncMock())

        await start.cmd_cancel(message, state)

        state.clear.assert_awaited_once()
        message.answer.assert_awaited_once()


class CreationFlowTests(unittest.IsolatedAsyncioTestCase):
    async def test_inline_create_entry_shows_style_keyboard(self) -> None:
        callback = CallbackQuery(
            id="test",
            from_user=TelegramUser(id=1001, is_bot=False, first_name="test"),
            chat_instance="test",
            data="mn:create",
        )
        state = SimpleNamespace(set_state=AsyncMock(), clear=AsyncMock())
        chats = SimpleNamespace(get_draft=AsyncMock(return_value=None),
                                count_all=AsyncMock(return_value=0))
        limits = SimpleNamespace(max_chats=lambda premium: 10)
        services = {"chats": chats, "limits": limits}

        with (
            patch.object(create, "get_services", return_value=services),
            patch.object(create, "get_db_user", return_value=None),
            patch.object(create.screens, "show", new_callable=AsyncMock) as show,
        ):
            await create.open_creation(callback, state)

        show.assert_awaited_once()
        self.assertIsNotNone(show.await_args.args[2])

    async def test_ai_is_cleanly_disabled_without_api_key(self) -> None:
        with patch.object(settings, "openrouter_api_key", ""):
            with self.assertRaises(AIUnavailableError):
                await AIService().generate("вымышленный диалог")


class AIEntryTests(unittest.IsolatedAsyncioTestCase):
    def test_openrouter_base_url_normalizes_to_chat_completions_endpoint(self) -> None:
        base = "https://openrouter.ai/api/v1"
        endpoint = f"{base}/chat/completions"

        self.assertEqual(AIService._completion_url(base), endpoint)
        self.assertEqual(AIService._completion_url(f"{base}/"), endpoint)
        self.assertEqual(AIService._completion_url(endpoint), endpoint)
        self.assertEqual(AIService._completion_url(""), endpoint)

    async def test_ai_entry_button_opens_prompt_state(self) -> None:
        from bot.services.ai_service import ai_service

        state = SimpleNamespace(set_state=AsyncMock(), clear=AsyncMock())
        message = SimpleNamespace(answer=AsyncMock())
        with (
            patch.object(ai_service, "api_key", "test-key"),
            patch.object(menu_handlers.screens, "ask", new_callable=AsyncMock,
                         return_value=True) as ask,
        ):
            await menu_handlers.open_ai_entry(message, state)

        state.set_state.assert_awaited_once_with(Flow.ai_prompt)
        ask.assert_awaited_once()
        self.assertIn("вымышленный", ask.await_args.args[1])

    async def test_ai_entry_shows_configuration_help_when_disabled(self) -> None:
        from bot.services.ai_service import ai_service

        state = SimpleNamespace(set_state=AsyncMock(), clear=AsyncMock())
        message = SimpleNamespace(answer=AsyncMock())
        with patch.object(ai_service, "api_key", ""):
            await menu_handlers.open_ai_entry(message, state)

        state.clear.assert_awaited_once()
        message.answer.assert_awaited_once()
        self.assertIn("OpenRouter", message.answer.await_args.args[0])

    async def test_ai_prompt_creates_draft_and_opens_editor(self) -> None:
        from bot.services.ai_service import ai_service

        generated = ChatConfig(
            title="Сценарий",
            participants=[
                Participant(name="Алиса", side=0),
                Participant(name="Боб", side=1),
            ],
            messages=[Message(text="Привет", side=0, author_index=0)],
        )
        status = SimpleNamespace(edit_text=AsyncMock(), delete=AsyncMock())
        message = SimpleNamespace(
            text="Придумай короткий вымышленный диалог",
            from_user=SimpleNamespace(id=1001),
            answer=AsyncMock(return_value=status),
        )
        state = SimpleNamespace(
            set_state=AsyncMock(),
            update_data=AsyncMock(),
        )
        chat = SimpleNamespace(id=42)
        chats = SimpleNamespace(
            count_all=AsyncMock(return_value=0),
            create=AsyncMock(return_value=(chat, ChatConfig())),
            save=AsyncMock(),
        )
        users = SimpleNamespace(count_chat=AsyncMock(), count_ai=AsyncMock())
        limits = SimpleNamespace(
            max_chats=lambda premium: 10,
            reserve_ai=AsyncMock(return_value=True),
        )

        with (
            patch.object(ai_service, "api_key", "test-key"),
            patch.object(ai_service, "generate", new_callable=AsyncMock,
                         return_value=generated) as generate,
            patch.object(
                ai_handlers, "get_services",
                return_value={"chats": chats, "user": users, "limits": limits},
            ),
            patch.object(ai_handlers, "is_premium", return_value=False),
            patch("bot.handlers.editor.show_editor", new_callable=AsyncMock) as show,
        ):
            await ai_handlers.on_ai_prompt(message, state)

        generate.assert_awaited_once_with("Придумай короткий вымышленный диалог")
        chats.create.assert_awaited_once_with(
            1001, style="telegram", template="ai", is_draft=True
        )
        chats.save.assert_awaited_once_with(1001, 42, generated)
        users.count_chat.assert_awaited_once_with(1001)
        users.count_ai.assert_awaited_once_with(1001)
        state.set_state.assert_awaited_once_with(Flow.editor)
        show.assert_awaited_once()
        self.assertIsInstance(
            message.answer.await_args_list[-1].kwargs["reply_markup"],
            ReplyKeyboardRemove,
        )

    def test_ai_generated_config_keeps_disclaimer_disabled_by_default(self) -> None:
        config = AIService.build_config(
            {
                "title": "Сценарий",
                "participants": [{"name": "А"}, {"name": "Б"}],
                "messages": [{"author": 0, "text": "Привет"}],
            }
        )

        self.assertEqual(config.disclaimer, "")

    def test_ai_entry_is_reachable_from_main_and_style_menus(self) -> None:
        main_callbacks = [
            button.callback_data
            for row in common_kb.main_menu_inline().inline_keyboard
            for button in row
        ]
        style_callbacks = [
            button.callback_data
            for row in style_menu().inline_keyboard
            for button in row
        ]

        self.assertIn("ai:ask", main_callbacks)
        self.assertIn("ai:ask", style_callbacks)
        self.assertIn(
            common_kb.BTN_AI,
            [
                button.text
                for row in common_kb.main_menu().keyboard
                for button in row
            ],
        )


class PersistenceAndLimitTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:", poolclass=StaticPool
        )
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()

    async def test_chat_foreign_key_cascades_when_user_is_deleted(self) -> None:
        async with self.sessions() as session:
            session.add(User(id=1))
            session.add(Chat(user_id=1, config={}))
            await session.commit()
            await session.execute(delete(User).where(User.id == 1))
            await session.commit()
            chats = await session.execute(select(Chat))

        self.assertEqual(chats.scalars().all(), [])

    async def test_concurrent_user_registration_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "registration.sqlite3"
            engine = create_async_engine(
                URL.create("sqlite+aiosqlite", database=str(db_path)),
                connect_args={"timeout": 30},
            )
            try:
                async with engine.begin() as connection:
                    await connection.run_sync(Base.metadata.create_all)
                sessions = async_sessionmaker(engine, expire_on_commit=False)

                async def register():
                    async with sessions() as session:
                        user, created = await UserRepository(session).get_or_create(
                            1001,
                            username="test_user",
                            first_name="Test",
                        )
                        await session.commit()
                        return user.id, created

                results = await asyncio.gather(*(register() for _ in range(10)))

                async with sessions() as session:
                    users = await session.execute(select(User))
                self.assertEqual([user_id for user_id, _ in results], [1001] * 10)
                self.assertEqual(sum(created for _, created in results), 1)
                self.assertEqual(len(users.scalars().all()), 1)
            finally:
                await engine.dispose()

    async def test_action_limit_blocks_only_after_allowed_actions(self) -> None:
        previous_limit = settings.limit_actions_per_minute
        settings.limit_actions_per_minute = 2
        try:
            async with self.sessions() as session:
                limits = LimitService(session)
                for _ in range(2):
                    self.assertTrue(await limits.check_spam(7))
                    await UsageRepository(session).log(7, "action")
                self.assertFalse(await limits.check_spam(7))
        finally:
            settings.limit_actions_per_minute = previous_limit

    async def test_image_attempts_and_ai_requests_are_reserved_before_work(self) -> None:
        old_image_limit = settings.limit_image_per_hour
        old_ai_limit = settings.limit_ai_per_hour
        settings.limit_image_per_hour = 1
        settings.limit_ai_per_hour = 1
        try:
            async with self.sessions() as session:
                limits = LimitService(session)
                self.assertTrue(await limits.reserve_image(21))
                self.assertFalse(await limits.reserve_image(21))
                self.assertTrue(await limits.reserve_ai(22))
                self.assertFalse(await limits.reserve_ai(22))
        finally:
            settings.limit_image_per_hour = old_image_limit
            settings.limit_ai_per_hour = old_ai_limit

    async def test_broadcast_confirmation_is_single_use_and_cancellable(self) -> None:
        async with self.sessions() as session:
            repo = BroadcastRepository(session)
            cancelled = await repo.create(11, "cancel me")
            await session.commit()
            self.assertTrue(await repo.cancel_pending(cancelled.id, 11))
            await session.commit()
            self.assertIsNone(await repo.claim_pending(cancelled.id, 11))

            ready = await repo.create(11, "send once")
            await session.commit()
            self.assertIsNotNone(await repo.claim_pending(ready.id, 11))
            await session.commit()
            self.assertIsNone(await repo.claim_pending(ready.id, 11))

    async def test_chat_service_create_save_edit_finish_reopen_and_delete(self) -> None:
        async with self.sessions() as session:
            session.add(User(id=31, first_name="Owner"))
            await session.flush()
            chats = ChatService(session)
            chat, config = await chats.create(31, style="telegram")
            config.participants[0].name = "Алиса"
            config.participants[1].name = "Боб"
            config.messages.extend(
                [
                    Message(text="Привет\n\nHello 🙂", side=0, author_index=0),
                    Message(text="Ответ", side=1, author_index=1),
                ]
            )
            await chats.save(31, chat.id, config)
            await session.commit()

            reopened = await chats.get_config(31, chat.id)
            reopened.messages[0].text = "Изменено"
            await chats.finish(31, chat.id, reopened)
            await session.commit()
            saved = await chats.get_chat(31, chat.id)
            self.assertIsNotNone(saved)
            self.assertFalse(saved.is_draft)
            self.assertEqual((await chats.get_config(31, chat.id)).messages[0].text, "Изменено")
            self.assertIsNone(await chats.get_chat(32, chat.id))

            copy = await chats.duplicate(31, chat.id)
            await session.commit()
            self.assertEqual((await chats.get_config(31, copy.id)).messages[0].text, "Изменено")
            await chats.delete(31, chat.id)
            await session.commit()
            self.assertIsNone(await chats.get_chat(31, chat.id))


class RendererTests(unittest.TestCase):
    def _config(self, count: int) -> ChatConfig:
        config = ChatConfig(style="telegram")
        config.settings.date_dividers = False
        config.participants = [Participant(name="А", side=0), Participant(name="Б", side=1)]
        config.messages = [
            Message(text=f"message-{index}", side=index % 2, author_index=index % 2)
            for index in range(count)
        ]
        return config

    def test_renders_empty_one_two_ten_and_hundred_messages(self) -> None:
        old_max = settings.render_max_height
        settings.render_max_height = 0
        try:
            for count in (0, 1, 2, 10, 50, 100, 101):
                with self.subTest(message_count=count):
                    image = get_renderer("telegram", width=1080).render(self._config(count))
                    self.assertEqual(image.width, 1080)
                    self.assertGreater(image.height, 0)
        finally:
            settings.render_max_height = old_max

    def test_renders_long_multiline_text_in_each_style(self) -> None:
        old_max = settings.render_max_height
        settings.render_max_height = 0
        try:
            for style in AVAILABLE_STYLES:
                with self.subTest(style=style.key):
                    config = self._config(2)
                    config.style = style.key
                    config.messages[0].text = (
                        "Первая строка\n\n"
                        + ("Mixed русский English 🙂 punctuation <>&? " * 50)
                    )
                    image = get_renderer(style.key, width=1080).render(config)
                    self.assertEqual(image.width, 1080)
                    self.assertGreater(image.height, 0)
        finally:
            settings.render_max_height = old_max

    def test_renders_media_reactions_replies_and_date_dividers(self) -> None:
        config = self._config(0)
        config.settings.date_dividers = True
        first = Message(
            text="Медиа",
            side=0,
            author_index=0,
            reaction=Reaction(emoji="❤️", count=2),
        )
        config.messages = [
            first,
            Message(
                text="Ответ",
                side=1,
                author_index=1,
                reply_to=first.id,
                media=MediaItem(kind=MessageKind.IMAGE, caption="ссылка https://example.com"),
                kind=MessageKind.IMAGE,
            ),
            Message(kind=MessageKind.VOICE, media=MediaItem(kind=MessageKind.VOICE)),
            Message(kind=MessageKind.FILE, media=MediaItem(kind=MessageKind.FILE)),
            Message(kind=MessageKind.STICKER, media=MediaItem(kind=MessageKind.STICKER)),
            Message(kind=MessageKind.SERVICE, text="Системное сообщение"),
            Message(kind=MessageKind.DATE, text="Вчера"),
        ]
        old_max = settings.render_max_height
        settings.render_max_height = 0
        try:
            image = get_renderer("telegram", width=1080).render(config)
        finally:
            settings.render_max_height = old_max

        self.assertEqual(image.width, 1080)
        self.assertGreater(image.height, 0)

    def test_height_cap_keeps_newest_message_and_fits_canvas(self) -> None:
        config = self._config(12)
        renderer = get_renderer("telegram", width=1080)
        renderer.settings = config.settings
        newest_layout = renderer.layout(config.messages[-1], config, len(config.messages) - 1)
        padding = renderer._bottom_padding(config)
        max_height = renderer.header_height + padding + newest_layout.height
        old_max = settings.render_max_height
        settings.render_max_height = max_height
        painted: list[str] = []
        original_paint = renderer.paint_message

        def record_paint(image, draw, layout, chat_config, y):
            painted.append(layout.message.text)
            return original_paint(image, draw, layout, chat_config, y)

        renderer.paint_message = record_paint
        try:
            image = renderer.render(config)
        finally:
            settings.render_max_height = old_max

        self.assertLessEqual(image.height, max_height)
        self.assertEqual(painted, ["message-11"])

    def test_rejects_height_cap_that_cannot_fit_newest_message(self) -> None:
        config = self._config(1)
        old_max = settings.render_max_height
        settings.render_max_height = 1
        try:
            with self.assertRaises(RenderError):
                get_renderer("telegram", width=1080).render(config)
        finally:
            settings.render_max_height = old_max


class RenderServiceSmokeTests(unittest.IsolatedAsyncioTestCase):
    async def test_render_service_produces_valid_png_for_long_chat(self) -> None:
        config = ChatConfig(style="telegram")
        config.settings.date_dividers = False
        config.participants = [
            Participant(name="Алиса", side=0),
            Participant(name="Боб", side=1),
        ]
        config.messages = [
            Message(
                text=(
                    "Русский текст, English, emoji 🙂\n\n"
                    + ("длинное содержимое <>& example.org " * 30 if index == 99 else "OK")
                ),
                side=index % 2,
                author_index=index % 2,
            )
            for index in range(100)
        ]

        data = await RenderService().render_bytes(config)
        with Image.open(io.BytesIO(data)) as image:
            image.verify()

        self.assertTrue(data.startswith(b"\x89PNG\r\n\x1a\n"))
        with Image.open(io.BytesIO(data)) as image:
            self.assertLessEqual(image.width + image.height, 10_000)
        self.assertLess(len(data), 10_000_000)


if __name__ == "__main__":
    unittest.main()
