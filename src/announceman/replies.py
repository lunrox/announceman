from datetime import datetime, timedelta
from typing import Optional, AsyncGenerator, List, Union

from aiogram.enums import ParseMode
from aiogram.types import (Message, LinkPreviewOptions, InlineKeyboardMarkup,
                           InlineKeyboardButton, ReplyKeyboardRemove, InputFile)
from aiogram.types.input_file import DEFAULT_CHUNK_SIZE
from pydantic.dataclasses import dataclass

from announceman import config
from announceman.route_preview import Route


def get_picker_keyboard(current_hour: int, current_minute: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='↑', callback_data=config.PICKER_UP_HOUR_DATA), InlineKeyboardButton(text='↑', callback_data=config.PICKER_UP_MINUTE_DATA)],
        [InlineKeyboardButton(text=f'{current_hour:02}', callback_data=config.NO_ACTION_DATA), InlineKeyboardButton(text=f'{current_minute:02}', callback_data=config.NO_ACTION_DATA)],
        [InlineKeyboardButton(text='↓', callback_data=config.PICKER_DOWN_HOUR_DATA), InlineKeyboardButton(text='↓', callback_data=config.PICKER_DOWN_MINUTE_DATA)],
        [InlineKeyboardButton(text='Save', callback_data=config.PICKER_SAVE_DATA)],
        config.KEYBOARD_SERVICE_LINE,
    ])


@dataclass
class Announcement:
    route_preview: Union[bytes, str]
    date: str
    track: str
    time: str
    start_point: str
    pace: str


class InMemoryInputFile(InputFile):
    def __init__(self, data: bytes, filename: Optional[str] = None, chunk_size: int = DEFAULT_CHUNK_SIZE):
        super().__init__(filename, chunk_size)
        self.bytes = data

    async def read(self, bot: "Bot") -> AsyncGenerator[bytes, None]:  # pragma: no cover
        offset = 0
        while offset < len(self.bytes):
            chunk = self.bytes[offset:offset + self.chunk_size]
            offset += self.chunk_size
            yield chunk


async def canceled(message: Message):
    await message.answer("Cancelled.", reply_markup=ReplyKeyboardRemove())


async def ask_for_date(message: Message):
    await message.reply(
        "Pick a date",
        parse_mode=ParseMode.MARKDOWN,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Tomorrow", callback_data=(datetime.now(tz=config.TZ) + timedelta(days=1)).strftime("%B %d")),
                InlineKeyboardButton(text="Today", callback_data=datetime.now(tz=config.TZ).strftime("%B %d")),
            ],
            [config.KEYBOARD_RESTART],
        ])
    )


async def show_route_list(routes: List[Route], message: Message, page_offset: int):
    route_previews = [
        f'{route.preview_message}\n{route.length} | {route.elevation} --> /route\_{i}\n'
        for i, route in enumerate(routes)
    ]
    offset = int(page_offset) * config.ROUTE_LIST_PAGE_LEN

    await message.edit_text(
        "\n".join(route_previews[offset:offset + config.ROUTE_LIST_PAGE_LEN]),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text=str(i), callback_data=str(i) if i != page_offset else config.NO_ACTION_DATA)
                for i in range(len(route_previews) // config.ROUTE_LIST_PAGE_LEN + 1)
            ],
            config.KEYBOARD_SERVICE_LINE,
        ])
    )


async def ask_for_time(message: Message, current_hour: int, current_minute: int):
    await message.edit_text(
        "Pick a time",
        reply_markup=get_picker_keyboard(current_hour=current_hour, current_minute=current_minute),
    )


async def ask_for_pace(message: Message):
    await message.reply(
        "Define a pace",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Easy", callback_data="Easy"),
                    InlineKeyboardButton(text="Z2", callback_data="Z2"),
                    InlineKeyboardButton(text="FAST", callback_data="FAST"),
                ],
                config.KEYBOARD_SERVICE_LINE,
            ],
        ),
    )


async def send_announcement(announcement: Announcement, message: Message):
    if isinstance(announcement.route_preview, bytes):
        route_preview = InMemoryInputFile(announcement.route_preview)
    else:
        route_preview = announcement.route_preview

    reply_obj = await message.reply_photo(
        route_preview,
        f"Announcement ({announcement.date})\n\n"
        f"{announcement.track}\n"
        f"{announcement.time} at {announcement.start_point}\n"
        f"Pace: {announcement.pace}",
        reply_markup=ReplyKeyboardRemove(),
    )
    return reply_obj.photo[0].file_id


async def ask_for_starting_point(starting_points: List["StartPoint"], message: Message):
    await message.reply(
        f"Choose a starting point:\n{"\n".join(f"{sp.formatted} --> /sp\_{i}" for i, sp in enumerate(starting_points))}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[config.KEYBOARD_SERVICE_LINE]),
    )


async def send_links(routes: List[str], start_points: List[str], message: Message):
    await message.reply(
        "Routes:\n" + "\n".join(routes) + "\n\nStart Points:\n" + "\n".join(start_points)
    )
