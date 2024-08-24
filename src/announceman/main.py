import asyncio
import json
import logging
import os.path
import pickle
import sys
from datetime import datetime, timedelta
from os import getenv

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton,
    LinkPreviewOptions, CallbackQuery,
)
from attr import dataclass

from announceman.route_preview import get_route_preview, load_route

TOKEN = getenv("BOT_TOKEN")
ROUTE_LIST_PAGE_LEN = 10
ROUTES_PATH = "announceman_data/routes.json"
ROUTES_CACHE = "announceman_data/.routes_loaded.pickle"
START_POINTS_PATH = "announceman_data/starting_points.json"
GO_BACK_DATA = "gobackdata"
RESTART_DATA = "restartdata"

routes = []
start_points = {}
form_router = Router()


@dataclass
class StartPoint:
    name: str
    link: str

    @property
    def formatted(self) -> str:
        return f"[{self.name}]({self.link})"


class Form(StatesGroup):
    date = State()
    time = State()
    track = State()
    start_point = State()
    pace = State()
    announcement = State()
    # also add contact info of the user


@form_router.message(CommandStart())
async def command_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(Form.date)

    await message.reply(
        "Pick a date\n\nOr reply with a custom one",
        parse_mode=ParseMode.MARKDOWN,
        link_preview_options=LinkPreviewOptions(is_disabled=True),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="Today", callback_data=datetime.now().strftime("%B %d")),
                InlineKeyboardButton(
                    text="Tomorrow", callback_data=(datetime.now() + timedelta(days=1)).strftime("%B %d"))
            ],
            [InlineKeyboardButton(text="Restart", callback_data=RESTART_DATA)],
        ])
    )


@form_router.message(Command("cancel"))
@form_router.message(F.text.casefold() == "cancel")
async def cancel_handler(message: Message, state: FSMContext) -> None:
    """
    Allow user to cancel any action
    """
    current_state = await state.get_state()
    if current_state is None:
        return

    logging.info("Cancelling state %r", current_state)
    await state.clear()
    await message.answer("Cancelled.", reply_markup=ReplyKeyboardRemove())


@form_router.callback_query()
async def callback_query_handler(callback_query: CallbackQuery, state: FSMContext) -> None:
    callback_data = callback_query.data
    form_state = await state.get_state()
    stack = (await state.get_data()).get('stack', [])
    if callback_data == RESTART_DATA:
        return await command_start(callback_query.message, state)
    elif callback_data == GO_BACK_DATA:
        try:
            stack.pop()
            form_state_name, callback_data = stack.pop()
        except IndexError:
            return await command_start(callback_query.message, state)
    else:
        form_state_name = str(form_state)

    if form_state_name != Form.track:
        stack.append((form_state_name, callback_data))

    async def show_route_list(offset):
        route_previews = [f"{route.preview_message} --> /route\_{i}" for i, route in enumerate(routes)]
        offset = int(offset) * ROUTE_LIST_PAGE_LEN
        await callback_query.message.edit_text(
            "\n".join(route_previews[offset:offset + ROUTE_LIST_PAGE_LEN]),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text=str(i), callback_data=str(i))
                    for i in range(len(route_previews) // ROUTE_LIST_PAGE_LEN + 1)
                ],
                [
                    InlineKeyboardButton(text="Go back", callback_data=GO_BACK_DATA),
                    InlineKeyboardButton(text="Restart", callback_data=RESTART_DATA),
                ]
            ])
        )

    if form_state_name == Form.date:
        await state.update_data(date=callback_data, stack=stack)
        await state.set_state(Form.time)

        await callback_query.message.edit_text(
            "Pick a time",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text=start_time, callback_data=start_time)
                        for start_time in ['07:00', '07:30', '08:00', '08:30', '09:00']
                    ],
                    [
                        InlineKeyboardButton(text="Go back", callback_data=GO_BACK_DATA),
                        InlineKeyboardButton(text="Restart", callback_data=RESTART_DATA),
                    ]
                ],
            ),
        )
    elif form_state_name == Form.time:
        await state.update_data(time=callback_data, stack=stack)
        await state.set_state(Form.track)
        await show_route_list(0)
    elif form_state_name == Form.track:
        if callback_data.startswith('/route_'):
            await process_track_data(callback_data, callback_query.message, state)
        else:
            try:
                await show_route_list(callback_data)
            except Exception as e:
                print(e)

    elif form_state_name == Form.start_point:
        sp = start_points.get(callback_data)
        sp = sp.formatted if sp else callback_data
        await state.update_data(start_point=sp, stack=stack)
        await state.set_state(Form.pace)

        await callback_query.message.edit_text(
            "Define a pace",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(text="Skip", callback_data="skip"),
                        InlineKeyboardButton(text="Easy", callback_data="easy/recovery"),
                        InlineKeyboardButton(text="Z2", callback_data="Z2"),
                        InlineKeyboardButton(text="Fast", callback_data="FAST"),
                    ],
                    [
                        InlineKeyboardButton(text="Go back", callback_data=GO_BACK_DATA),
                        InlineKeyboardButton(text="Restart", callback_data=RESTART_DATA),
                    ]
                ],
            ),
        )
    elif form_state_name == Form.pace:
        data = await state.get_data()
        data['pace'] = callback_data

        await callback_query.message.reply(
            f"Announcement ({data['date']})\n\n"
            f"{data['track']}\n"
            f"{data['time']} at {data['start_point']}\n"
            f"Pace: {data['pace']}",
            reply_markup=ReplyKeyboardRemove(),
        )
        await state.clear()


async def process_track_data(track_command, message: Message, state: FSMContext) -> None:
    if not track_command.startswith('/route_'):
        return

    idx = int(track_command.split('_')[1])
    route = routes[idx]

    data = await state.get_data()
    data['stack'].append((str(await state.get_state()), track_command))
    await state.update_data(track=route.preview_message, route=route, stack=data['stack'])
    await state.set_state(Form.start_point)
    await message.reply(
        "Choose a starting point",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text=sp, callback_data=sp) for sp in start_points
                ],
                [
                    InlineKeyboardButton(text="Go back", callback_data=GO_BACK_DATA),
                    InlineKeyboardButton(text="Restart", callback_data=RESTART_DATA),
                ]
            ],
        ),
    )


@form_router.message(Form.track)
async def process_track(message: Message, state: FSMContext) -> None:
    await process_track_data(message.text, message, state)


@form_router.message(Command("preview"))
async def preview_handler(message: Message, command: CommandObject) -> None:
    if not command.args:
        await message.answer(
            "Please send route URL with your preview command",
            reply_markup=ReplyKeyboardRemove(),
        )
    picture = await get_route_preview(command.args)
    await message.reply_photo(picture)


async def main():
    global routes
    if os.path.exists(ROUTES_CACHE):
        with open(ROUTES_CACHE, 'rb') as f:
            routes = pickle.load(f)
    else:
        with open(ROUTES_PATH, 'r') as f_route:
            route_links = json.load(f_route)
        routes = [load_route(link, name) for name, link in route_links.items()]
        with open(ROUTES_CACHE, 'wb') as f_cache:
            pickle.dump(routes, f_cache)

    global start_points
    with open(START_POINTS_PATH, 'r') as f_start_points:
        start_points = {name: StartPoint(name, link) for name, link in json.load(f_start_points).items()}

    # Initialize Bot instance with default bot properties which will be passed to all API calls
    bot = Bot(token=TOKEN, default=DefaultBotProperties(
        parse_mode=ParseMode.MARKDOWN,
        disable_notification=True,
        link_preview_is_disabled=True,
    ))

    dp = Dispatcher()

    dp.include_router(form_router)

    # Start event dispatching
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
