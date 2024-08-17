import asyncio
import logging
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
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from announceman.route_preview import get_route_preview

TOKEN = getenv("BOT_TOKEN")

form_router = Router()


class Form(StatesGroup):
    date = State() # today, tomorrow or custom
    time = State()  # presets or custom
    track = State()  # initially - only custom
    title = State()  # take name from the track or ask for custom text from the user
    start_point = State()  # initially - only custom
    summary = State()  # some base info
    pace = State() # have presets for it
    is_it_a_drop_ride = State() # drop/nodrop
    post_scriptum = State() # extra info at the end
    # lang?
    # also add contact info of the user


@form_router.message(CommandStart())
async def command_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(Form.date)

    await message.answer(
        "Pick a date",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Today"), KeyboardButton(text="Tomorrow")]],
            one_time_keyboard=True,
            input_field_placeholder="Input your custom date here...",
        )
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
    await message.answer(
        "Cancelled.",
        reply_markup=ReplyKeyboardRemove(),
    )


@form_router.message(Form.date)
async def process_date(message: Message, state: FSMContext) -> None:
    if message.text == "Today":
        date = datetime.now().strftime("%B %d")
    elif message.text == "Tomorrow":
        date = (datetime.now() + timedelta(days=1)).strftime("%B %d")
    else:
        date = message.text

    await state.update_data(date=date)
    await state.set_state(Form.time)
    await message.answer(
        "Pick a time",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [
                    KeyboardButton(text="07:00"),
                    KeyboardButton(text="07:30"),
                    KeyboardButton(text="08:00"),
                ]
            ],
            resize_keyboard=True,
            one_time_keyboard=True,
            input_field_placeholder="Input your custom time here...",
        ),
    )


@form_router.message(Form.time)
async def process_time(message: Message, state: FSMContext) -> None:
    await state.update_data(time=message.text)
    await state.set_state(Form.track)

    await message.reply(
        "Add a link to the route",
        reply_markup=ReplyKeyboardRemove(),
    )


@form_router.message(Form.track)
async def process_track(message: Message, state: FSMContext) -> None:
    await state.update_data(track=message.text)
    await state.set_state(Form.title)

    # todo: get name of the track from strava or komoot and use it as a preset for a button

    await message.reply(
        "Enter the title",
        reply_markup=ReplyKeyboardRemove(),
    )


@form_router.message(Form.title)
async def process_title(message: Message, state: FSMContext) -> None:
    await state.update_data(title=message.text)
    await state.set_state(Form.start_point)

    await message.reply(
        "Choose a starting point",
        reply_markup=ReplyKeyboardRemove(),
    )


@form_router.message(Form.start_point)
async def process_start_point(message: Message, state: FSMContext) -> None:
    await state.update_data(start_point=message.text)
    await state.set_state(Form.summary)

    await message.reply(
        "Describe your ride",
        reply_markup=ReplyKeyboardRemove(),
    )


@form_router.message(Form.summary)
async def process_summary(message: Message, state: FSMContext) -> None:
    await state.update_data(summary=message.text)
    await state.set_state(Form.pace)

    await message.reply(
        "Define the pace",
        reply_markup=ReplyKeyboardRemove(),
    )


@form_router.message(Form.pace)
async def process_pace(message: Message, state: FSMContext) -> None:
    await state.update_data(pace=message.text)
    await state.set_state(Form.is_it_a_drop_ride)

    await message.reply(
        "Is it a drop ride?",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="No"), KeyboardButton(text="Yes")]],
            resize_keyboard=True,
            one_time_keyboard=True,
        ),
    )


@form_router.message(Form.is_it_a_drop_ride)
async def process_drop_ride(message: Message, state: FSMContext) -> None:
    if message.text not in {"No", "Yes"}:
        return

    await state.update_data(drop_ride=message.text == "Yes")
    await state.set_state(Form.post_scriptum)

    await message.reply(
        "Any extra comments you want to add?",
        reply_markup=ReplyKeyboardRemove(),
    )


@form_router.message(Form.post_scriptum)
async def process_post_scriptum(message: Message, state: FSMContext) -> None:
    data = await state.update_data(post_scriptum=message.text)

    await message.reply(
        f"Announcement ({data['date']})\n"
        f"{data['title']}\n"
        f"{data['track']}\n"
        f"{data['summary']}\n"
        f"{data['start_point']} at {data['time']}\n\n"
        f"{data['summary']}\n"
        f"pace: {data['pace']} ({"No-drop ride" if data['drop_ride'] else "Drop ride"})\n\n"
        f"{data['post_scriptum']}",
        reply_markup=ReplyKeyboardRemove(),
    )

    await state.clear()


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
    # Initialize Bot instance with default bot properties which will be passed to all API calls
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))

    dp = Dispatcher()

    dp.include_router(form_router)

    # Start event dispatching
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
