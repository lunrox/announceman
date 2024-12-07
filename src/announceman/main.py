import asyncio
import json
import logging
import os.path
import pickle
import sys
from typing import Tuple, List, Union

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

from announceman import replies, config
from announceman.route_preview import load_route


LOG = logging.getLogger(__name__)
routes = []
start_points = []
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
    LOG.info("Sending links")
    await replies.send_links(
        routes=[route.preview_message for route in routes],
        start_points=[sp.formatted for sp in start_points],
        message=message,
    )


@form_router.message(Form.track)
async def process_track(message: Message, state: FSMContext) -> None:
    await process_track_data(message.text, message, state)


@form_router.message(Form.start_point)
async def process_start_point(message: Message, state: FSMContext) -> None:
    await process_start_point_data(message.text, message, state)


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

    if callback_data == config.NO_ACTION_DATA:
        return

    if callback_data == config.RESTART_DATA:
        return await command_start(callback_query.message, state)
    elif callback_data == config.GO_BACK_DATA:
        try:
            stack.pop()
            form_state_name, callback_data = stack.pop()
        except IndexError:
            return await command_start(callback_query.message, state)
    else:
        form_state_name = str(form_state)

    if form_state_name not in {Form.track, Form.time, Form.start_point}:
        stack.append((form_state_name, callback_data))

    if form_state_name == Form.date:
        current_hour = state_data.get('current_hour', config.DEFAULT_HOUR)
        current_minute = state_data.get('current_minute', config.DEFAULT_MINUTE)
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
        if callback_data == config.PICKER_SAVE_DATA:
            saved_time = f'{current_hour:02}:{current_minute:02}'
            stack.append((form_state_name, callback_data))
            await state.update_data(time=saved_time, stack=stack)
            await state.set_state(Form.track)
            return await replies.show_route_list(routes, callback_query.message, page_offset=0)
        elif callback_data == config.PICKER_UP_HOUR_DATA:
            current_hour += 1
            if current_hour == 24:
                current_hour = 0
        elif callback_data == config.PICKER_DOWN_HOUR_DATA:
            current_hour -= 1
            if current_hour < 0:
                current_hour = 23
        elif callback_data == config.PICKER_UP_MINUTE_DATA:
            current_minute += 15
            if current_minute == 60:
                current_minute = 0
        elif callback_data == config.PICKER_DOWN_MINUTE_DATA:
            current_minute -= 15
            if current_minute < 0:
                current_minute = 45
        await state.update_data(stack=stack, current_hour=current_hour, current_minute=current_minute)
        await replies.ask_for_time(callback_query.message, current_hour, current_minute)
    elif form_state_name == Form.track:
        if callback_data.startswith('/route_'):
            await process_track_data(callback_data, callback_query.message, state)
        else:
            await replies.show_route_list(routes, callback_query.message, page_offset=int(callback_data))
    elif form_state_name == Form.start_point:
        await process_start_point_data(callback_data, callback_query.message, state)
    elif form_state_name == Form.pace:
        state_data['pace'] = callback_data
        route = routes[state_data['route_id']]
        LOG.info(f'Announcement made: {state_data}')
        state_data['route_preview'] = route.preview_id or route.preview_image
        route.preview_id = await replies.send_announcement(replies.Announcement(**state_data), callback_query.message)
        await state.clear()


async def get_stack_updated_by_command(command: str, state: FSMContext) -> List[Tuple[str, str]]:
    stack = (await state.get_data()).get('stack', [])
    stack.append((str(await state.get_state()), command))
    return stack


def get_id_from_command(command: str, prefix: str) -> Union[int, None]:
    if not command.startswith(prefix):
        return None
    return int(command.split('_')[1])


async def process_track_data(track_command, message: Message, state: FSMContext) -> None:
    route_id = get_id_from_command(track_command, '/route_')
    if route_id is None:
        return
    route = routes[route_id]

    stack = await get_stack_updated_by_command(track_command, state)
    await state.update_data(track=route.preview_message, route_id=route_id, stack=stack)
    await state.set_state(Form.start_point)
    await replies.ask_for_starting_point(start_points, message)


async def process_start_point_data(sp_command, message: Message, state: FSMContext) -> None:
    sp_id = get_id_from_command(sp_command, '/sp_')
    if sp_id is None:
        return
    sp = start_points[sp_id]

    stack = await get_stack_updated_by_command(sp_command, state)
    await state.update_data(start_point=sp.formatted, stack=stack)
    await state.set_state(Form.pace)
    await replies.ask_for_pace(message)


def load_routes():
    global routes
    if os.path.exists(config.ROUTES_CACHE):
        with open(config.ROUTES_CACHE, 'rb') as f:
            routes = pickle.load(f)
    else:
        with open(config.ROUTES_PATH, 'r') as f_route:
            route_links = json.load(f_route)
        with open(config.ROUTE_PREVIEWS_PATH, 'r') as f_route_previews:
            route_pics = json.load(f_route_previews)
        routes = list(sorted([load_route(link, name, route_pics.get(name)) for name, link in route_links.items()], key=lambda r: r.name))
        with open(config.ROUTES_CACHE, 'wb') as f_cache:
            pickle.dump(routes, f_cache)


def load_starting_points():
    global start_points
    with open(config.START_POINTS_PATH, 'r') as f_start_points:
        start_points = [
            StartPoint(name=name, link=link)
            for name, link in sorted(json.load(f_start_points).items(), key=lambda x: x[0])
        ]


async def main():
    load_routes()
    load_starting_points()

    bot = Bot(token=config.TOKEN, default=DefaultBotProperties(
        parse_mode=ParseMode.MARKDOWN,
        disable_notification=True,
        link_preview_is_disabled=True,
    ))

    dp = Dispatcher()
    dp.include_router(form_router)
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format='%(asctime)s %(levelname)s %(message)s')
    asyncio.run(main())
