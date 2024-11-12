import asyncio
import json
import logging
import os.path
import pickle
import sys
from os import getenv

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
)
from pydantic.dataclasses import dataclass

from announceman import replies
from announceman.replies import (
    PICKER_SAVE_DATA, PICKER_UP_HOUR_DATA, PICKER_DOWN_HOUR_DATA, PICKER_UP_MINUTE_DATA, PICKER_DOWN_MINUTE_DATA
)
from announceman.route_preview import load_route

TOKEN = getenv("BOT_TOKEN")
ROUTES_PATH = "announceman_data/routes.json"
ROUTES_CACHE = "announceman_data/.routes_loaded.pickle"
START_POINTS_PATH = "announceman_data/starting_points.json"
# time picker config
DEFAULT_HOUR = 10
DEFAULT_MINUTE = 0


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


@form_router.message(Command("cancel"))
@form_router.message(F.text.casefold() == "cancel")
async def cancel_handler(message: Message, state: FSMContext) -> None:
    current_state = await state.get_state()
    if current_state is None:
        return

    logging.info("Cancelling state %r", current_state)
    await state.clear()
    await replies.canceled(message)


@form_router.message(Command("links"))
@form_router.message(F.text.casefold() == "links")
async def links_handler(message: Message, state: FSMContext) -> None:
    await replies.send_links(
        routes=[route.preview_message for route in routes],
        start_points=[sp.formatted for sp in start_points.values()],
        message=message,
    )


@form_router.message(Form.track)
async def process_track(message: Message, state: FSMContext) -> None:
    await process_track_data(message.text, message, state)


@form_router.message()
@form_router.message(CommandStart())
async def command_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(Form.date)
    await replies.ask_for_date(message)


@form_router.callback_query()
async def callback_query_handler(callback_query: CallbackQuery, state: FSMContext) -> None:
    callback_data = callback_query.data
    form_state = await state.get_state()
    state_data = await state.get_data()
    stack = state_data.get('stack', [])
    print('state_data: {0}, stack: {1}, callback_data: {2}'.format(state_data, stack, callback_data))

    if callback_data == replies.RESTART_DATA:
        return await command_start(callback_query.message, state)
    elif callback_data == replies.GO_BACK_DATA:
        try:
            stack.pop()
            form_state_name, callback_data = stack.pop()
        except IndexError:
            return await command_start(callback_query.message, state)
    else:
        form_state_name = str(form_state)

    if form_state_name not in {Form.track, Form.time}:
        stack.append((form_state_name, callback_data))

    if form_state_name == Form.date:
        current_hour = state_data.get('current_hour', DEFAULT_HOUR)
        current_minute = state_data.get('current_minute', DEFAULT_MINUTE)
        await state.update_data(date=callback_data, stack=stack, current_hour=current_hour, current_minute=current_minute)
        await state.set_state(Form.time)
        await replies.ask_for_time(
            message=callback_query.message,
            current_hour=current_hour,
            current_minute=current_minute,
        )
    elif form_state_name == Form.time:
        current_hour = state_data['current_hour']
        current_minute = state_data['current_minute']
        if callback_data == PICKER_SAVE_DATA:
            saved_time = f'{current_hour:02}:{current_minute:02}'
            stack.append((form_state_name, saved_time))
            await state.update_data(time=saved_time, stack=stack)
            await state.set_state(Form.track)
            return await replies.show_route_list(routes, callback_query.message, offset=0)
        elif callback_data == PICKER_UP_HOUR_DATA:
            current_hour += 1
            if current_hour == 24:
                current_hour = 0
        elif callback_data == PICKER_DOWN_HOUR_DATA:
            current_hour -= 1
            if current_hour < 0:
                current_hour = 23
        elif callback_data == PICKER_UP_MINUTE_DATA:
            current_minute += 15
            if current_minute == 60:
                current_minute = 0
        elif callback_data == PICKER_DOWN_MINUTE_DATA:
            current_minute -= 15
            if current_minute < 0:
                current_minute = 45
        await state.update_data(stack=stack, current_hour=current_hour, current_minute=current_minute)
        await replies.ask_for_time(callback_query.message, current_hour, current_minute)
    elif form_state_name == Form.track:
        if callback_data.startswith('/route_'):
            await process_track_data(callback_data, callback_query.message, state)
        else:
            await replies.show_route_list(routes, callback_query.message, offset=callback_data)
    elif form_state_name == Form.start_point:
        sp = start_points.get(callback_data)
        sp = sp.formatted if sp else callback_data
        await state.update_data(start_point=sp, stack=stack)
        await state.set_state(Form.pace)
        await replies.ask_for_pace(callback_query.message)
    elif form_state_name == Form.pace:
        state_data['pace'] = callback_data
        route = routes[state_data['route_id']]
        state_data['route_preview'] = route.preview_id or route.preview_image
        route.preview_id = await replies.send_announcement(replies.Announcement(**state_data), callback_query.message)
        await state.clear()


async def process_track_data(track_command, message: Message, state: FSMContext) -> None:
    if not track_command.startswith('/route_'):
        return

    route_id = int(track_command.split('_')[1])
    route = routes[route_id]

    stack = (await state.get_data()).get('stack', [])
    stack.append((str(await state.get_state()), track_command))

    await state.update_data(track=route.preview_message, route_id=route_id, stack=stack)
    await state.set_state(Form.start_point)
    await replies.ask_for_starting_point(start_points.keys(), message)


def load_routes():
    global routes
    if os.path.exists(ROUTES_CACHE):
        with open(ROUTES_CACHE, 'rb') as f:
            routes = pickle.load(f)
    else:
        with open(ROUTES_PATH, 'r') as f_route:
            route_links = json.load(f_route)
        routes = list(sorted([load_route(link, name) for name, link in route_links.items()], key=lambda r: r.name))
        with open(ROUTES_CACHE, 'wb') as f_cache:
            pickle.dump(routes, f_cache)


def load_starting_points():
    global start_points
    with open(START_POINTS_PATH, 'r') as f_start_points:
        start_points = {
            name: StartPoint(name=name, link=link)
            for name, link in sorted(json.load(f_start_points).items(), key=lambda x: x[0])
        }


async def main():
    load_routes()
    load_starting_points()

    bot = Bot(token=TOKEN, default=DefaultBotProperties(
        parse_mode=ParseMode.MARKDOWN,
        disable_notification=True,
        link_preview_is_disabled=True,
    ))

    dp = Dispatcher()
    dp.include_router(form_router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
