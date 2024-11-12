from datetime import datetime, timedelta
from typing import Optional, AsyncGenerator, List, Iterable, Union

from aiogram.enums import ParseMode
from aiogram.types import (Message, LinkPreviewOptions, InlineKeyboardMarkup,
                           InlineKeyboardButton, ReplyKeyboardRemove, InputFile)
from aiogram.types.input_file import DEFAULT_CHUNK_SIZE
from pydantic.dataclasses import dataclass

from announceman.route_preview import Route

GO_BACK_DATA = "go-back-data"
RESTART_DATA = "restart-data"
ROUTE_LIST_PAGE_LEN = 10
KEYBOARD_RESTART = InlineKeyboardButton(text="Restart", callback_data=RESTART_DATA)
KEYBOARD_SERVICE_LINE = [
    InlineKeyboardButton(text="Go back", callback_data=GO_BACK_DATA),
    KEYBOARD_RESTART,
]
PICKER_UP_HOUR_DATA = "picker-up-hour-data"
PICKER_DOWN_HOUR_DATA = "picker-down-hour-data"
PICKER_UP_MINUTE_DATA = "picker-up-minute-data"
PICKER_DOWN_MINUTE_DATA = "picker-down-minute-data"
PICKER_SAVE_DATA = "picker-save-data"
NO_ACTION_DATA = "no-action-data"


def get_picker_keyboard(current_hour: int, current_minute: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='↑', callback_data=PICKER_UP_HOUR_DATA), InlineKeyboardButton(text='↑', callback_data=PICKER_UP_MINUTE_DATA)],
        [InlineKeyboardButton(text=f'{current_hour:02}', callback_data=NO_ACTION_DATA), InlineKeyboardButton(text=f'{current_minute:02}', callback_data=NO_ACTION_DATA)],
        [InlineKeyboardButton(text='↓', callback_data=PICKER_DOWN_HOUR_DATA), InlineKeyboardButton(text='↓', callback_data=PICKER_DOWN_MINUTE_DATA)],
        [InlineKeyboardButton(text='Save', callback_data=PICKER_SAVE_DATA)],
        KEYBOARD_SERVICE_LINE,
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
                    text="Tomorrow", callback_data=(datetime.now() + timedelta(days=1)).strftime("%B %d")),
                InlineKeyboardButton(text="Today", callback_data=datetime.now().strftime("%B %d")),
            ],
            [KEYBOARD_RESTART],
        ])
    )


async def show_route_list(routes: List[Route], message: Message, offset: int):
    route_previews = [
        f'{route.preview_message}\n{route.length} | {route.elevation} --> /route\_{i}\n'
        for i, route in enumerate(routes)
    ]
    offset = int(offset) * ROUTE_LIST_PAGE_LEN
    await message.edit_text(
        "\n".join(route_previews[offset:offset + ROUTE_LIST_PAGE_LEN]),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text=str(i), callback_data=str(i))
                for i in range(len(route_previews) // ROUTE_LIST_PAGE_LEN + 1)
            ],
            KEYBOARD_SERVICE_LINE,
        ])
    )


async def ask_for_time(message: Message, current_hour: int, current_minute: int):
    await message.edit_text(
        "Pick a time",
        reply_markup=get_picker_keyboard(current_hour=current_hour, current_minute=current_minute),
    )


async def ask_for_pace(message: Message):
    await message.edit_text(
        "Define a pace",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="Easy", callback_data="Easy"),
                    InlineKeyboardButton(text="Z2", callback_data="Z2"),
                    InlineKeyboardButton(text="FAST", callback_data="FAST"),
                ],
                KEYBOARD_SERVICE_LINE,
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


async def ask_for_starting_point(starting_point_names: Iterable[str], message: Message):
    await message.reply(
        "Choose a starting point",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                *[[InlineKeyboardButton(text=sp, callback_data=sp)] for sp in starting_point_names],
                KEYBOARD_SERVICE_LINE,
            ],
        ),
    )


async def send_links(routes: List[str], start_points: List[str], message: Message):
    await message.reply(
        "Routes:\n" + "\n".join(routes) + "\n\nStart Points:\n" + "\n".join(start_points)
    )
