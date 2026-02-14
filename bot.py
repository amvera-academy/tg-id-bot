import asyncio
import os
import re
import html

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatType, MessageEntityType, ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, KeyboardButtonRequestUsers, KeyboardButtonRequestChat, MessageOriginUser, MessageOriginHiddenUser, MessageOriginChat, MessageOriginChannel

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

USERNAME_RE = re.compile(r"@([A-Za-z0-9_]{5,32})")
TME_RE = re.compile(r"(?:https?://)?t\.me/([A-Za-z0-9_+/c\-]{3,})", re.IGNORECASE)
TG_RESOLVE_RE = re.compile(r"tg://resolve\?domain=([A-Za-z0-9_]{5,32})", re.IGNORECASE)


def kb_private():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(
                    text="👤 Выбрать пользователя",
                    request_users=KeyboardButtonRequestUsers(
                        request_id=1,
                        max_quantity=1,
                        request_name=True,
                        request_username=True,
                    ),
                )
            ],
            [
                KeyboardButton(
                    text="💬 Выбрать группу/супергруппу",
                    request_chat=KeyboardButtonRequestChat(
                        request_id=2,
                        chat_is_channel=False,
                        request_title=True,
                        request_username=True,
                    ),
                ),
                KeyboardButton(
                    text="📢 Выбрать канал",
                    request_chat=KeyboardButtonRequestChat(
                        request_id=3,
                        chat_is_channel=True,
                        request_title=True,
                        request_username=True,
                    ),
                ),
            ],
            [KeyboardButton(text="📇 Поделиться контактом", request_contact=True)],
        ],
        resize_keyboard=True,
        selective=True,
    )


def h(s: str):
    return html.escape(s or "")


def code_id(x):
    return f"<code>{x}</code>"


def b(s: str):
    return f"<b>{h(s)}</b>"


def i(s: str):
    return f"<i>{h(s)}</i>"


def mask_phone(phone: str):
    p = re.sub(r"\D+", "", phone or "")
    if len(p) <= 4:
        return phone
    return p[:2] + "****" + p[-2:]


def strip_username(u: str) -> str:
    return (u or "").strip().lstrip("@").lower()


def extract_usernames_from_text(text: str):
    res = set()

    for m in USERNAME_RE.finditer(text or ""):
        res.add(strip_username(m.group(1)))

    for m in TME_RE.finditer(text or ""):
        tail = (m.group(1) or "").strip().strip("/")
        if tail.startswith("c/") or tail.startswith("+") or tail.startswith("joinchat/"):
            continue
        if "/" in tail:
            tail = tail.split("/", 1)[0]
        if re.fullmatch(r"[A-Za-z0-9_]{5,32}", tail):
            res.add(strip_username(tail))

    for m in TG_RESOLVE_RE.finditer(text or ""):
        res.add(strip_username(m.group(1)))

    return sorted(res)


def add_block(blocks, header=None, kind=None, username=None, title=None, tg_id=None, extra=None):
    lines = []

    if header:
        lines.append(b(header))
        lines.append("")

    if kind:
        if kind == "Поиск…":
            lines.append(i(kind))
        else:
            lines.append(b(kind))

    if username:
        lines.append(b("@" + username))

    if title:
        lines.append(h(title))

    if tg_id is not None:
        lines.append("id: " + code_id(tg_id))

    if extra:
        for raw in extra.split("\n"):
            raw = raw.strip()
            if not raw:
                continue

            if raw.startswith("phone:"):
                val = raw.split(":", 1)[1].strip()
                lines.append("phone: " + code_id(h(val)))
                continue

            if raw.startswith("id:") and "скрыт настройками приватности" in raw:
                lines.append("id: " + i("скрыт настройками приватности"))
                continue

            lines.append(h(raw))

    blocks.append("\n".join(lines))


async def build_blocks(bot: Bot, m: Message):
    blocks = []

    if m.forward_origin:
        o = m.forward_origin

        if isinstance(o, MessageOriginUser):
            u = o.sender_user
            title = (u.first_name or "") + ((" " + u.last_name) if u.last_name else "")
            add_block(
                blocks,
                header="Обнаружена пересылка (форвард) сообщения!",
                kind="Пользователь",
                username=u.username,
                title=title,
                tg_id=u.id,
            )

        elif isinstance(o, MessageOriginHiddenUser):
            add_block(
                blocks,
                header="Обнаружена пересылка (форвард) сообщения!",
                kind="Пользователь",
                title=o.sender_user_name,
                extra="id: скрыт настройками приватности",
            )

        elif isinstance(o, MessageOriginChat):
            c = o.sender_chat
            add_block(
                blocks,
                header="Обнаружена пересылка (форвард) сообщения!",
                kind="Чат",
                username=c.username,
                title=c.title,
                tg_id=c.id,
            )

        elif isinstance(o, MessageOriginChannel):
            c = o.chat
            add_block(
                blocks,
                header="Обнаружена пересылка (форвард) сообщения!",
                kind="Канал",
                username=c.username,
                title=c.title,
                tg_id=c.id,
            )

        else:
            add_block(
                blocks,
                header="Обнаружена пересылка (форвард) сообщения!",
                kind="Источник",
                extra="Не удалось распознать тип",
            )

    if m.reply_to_message and m.reply_to_message.from_user:
        u = m.reply_to_message.from_user
        title = (u.first_name or "") + ((" " + u.last_name) if u.last_name else "")
        add_block(
            blocks,
            header="Обнаружен reply!",
            kind="Пользователь",
            username=u.username,
            title=title,
            tg_id=u.id,
        )

    if m.users_shared:
        for su in (m.users_shared.users or []):
            title = (su.first_name or "") + ((" " + su.last_name) if su.last_name else "")
            add_block(
                blocks,
                header="Обнаружен выбор пользователя!",
                kind="Пользователь",
                username=su.username,
                title=title,
                tg_id=su.user_id,
            )

    if m.chat_shared:
        add_block(
            blocks,
            header="Обнаружен выбор чата/канала!",
            kind="Чат",
            tg_id=m.chat_shared.chat_id,
        )

    if m.contact:
        title = (m.contact.first_name or "") + ((" " + m.contact.last_name) if m.contact.last_name else "")
        phone = mask_phone(m.contact.phone_number)

        if m.contact.user_id is None:
            add_block(
                blocks,
                header="Обнаружен контакт!",
                kind="Контакт",
                title=title,
                extra=f"phone: {phone}\nid: отсутствует (Telegram не приложил user_id)",
            )
        else:
            add_block(
                blocks,
                header="Обнаружен контакт!",
                kind="Пользователь",
                title=title,
                tg_id=m.contact.user_id,
                extra=f"phone: {phone}",
            )

    if m.entities and (m.text or ""):
        for e in m.entities:
            if e.type == MessageEntityType.TEXT_MENTION and e.user:
                u = e.user
                header_text = (m.text or "")[e.offset : e.offset + e.length]
                title = (u.first_name or "") + ((" " + u.last_name) if u.last_name else "")
                add_block(
                    blocks,
                    header=header_text,
                    kind="Пользователь",
                    username=u.username,
                    title=title,
                    tg_id=u.id,
                )

    text = (m.text or m.caption or "").strip()
    if text:
        usernames = extract_usernames_from_text(text)

        for uname in usernames:
            add_block(blocks, header=uname, kind="Поиск…")

            chat = None
            try:
                chat = await bot.get_chat("@" + uname)
            except Exception:
                chat = None

            if chat is not None:
                title = getattr(chat, "title", None) or getattr(chat, "first_name", None) or ""
                if chat.type == "channel":
                    kind = "Канал"
                elif chat.type in ("group", "supergroup"):
                    kind = "Чат"
                else:
                    kind = "Бот" if uname.lower().endswith("bot") else "Пользователь"

                add_block(
                    blocks,
                    kind=kind,
                    username=uname,
                    title=title if title else None,
                    tg_id=int(chat.id),
                )
            else:
                add_block(
                    blocks,
                    kind="Не удалось найти",
                    extra="Если это пользователь/бот - Bot API не может вернуть ID по @username.\n"
                          "Сделай reply/форвард, или нажми «Выбрать пользователя».",
                )

    if not blocks:
        add_block(
            blocks,
            kind="Чат",
            username=getattr(m.chat, "username", None),
            title=getattr(m.chat, "title", None),
            tg_id=int(m.chat.id),
        )
        if m.from_user:
            title = (m.from_user.first_name or "") + ((" " + m.from_user.last_name) if m.from_user.last_name else "")
            add_block(
                blocks,
                kind="Пользователь",
                username=m.from_user.username,
                title=title,
                tg_id=int(m.from_user.id),
            )

    return blocks


async def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN не установлен!")

    bot = Bot(
        BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    @dp.message(CommandStart())
    async def start(m: Message):
        text = (
            "👋 Привет!\n\n"
            "Пришли мне:\n"
            "- forward, \n"
            "- reply на сообщение, \n"
            "- контакт \n"
            "- или выбери чат/канал/пользователя\n\n"
            "И я пришлю тебе Telegram ID!"
        )
        if m.chat.type == ChatType.PRIVATE:
            await m.answer(text, reply_markup=kb_private())
        else:
            await m.answer(text)

    @dp.message()
    async def any_message(m: Message):
        blocks = await build_blocks(bot, m)
        out = "\n\n".join(blocks)

        if m.chat.type == ChatType.PRIVATE:
            await m.answer(out, reply_markup=kb_private(), disable_web_page_preview=True)
        else:
            await m.answer(out, disable_web_page_preview=True)

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
