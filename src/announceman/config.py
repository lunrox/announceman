from os import getenv
from zoneinfo import ZoneInfo

from aiogram.types import InlineKeyboardButton

TOKEN = getenv("BOT_TOKEN")
TZ = ZoneInfo(getenv("TZ", default="Asia/Tbilisi"))

# data files and cache
ROUTES_PATH = "announceman_data/routes.json"
ROUTES_CACHE = "announceman_data/.routes_loaded.pickle"
START_POINTS_PATH = "announceman_data/starting_points.json"

# UX config
DEFAULT_HOUR = 10
DEFAULT_MINUTE = 0
ROUTE_LIST_PAGE_LEN = 10

# callback data strings
GO_BACK_DATA = "go-back-data"
RESTART_DATA = "restart-data"
PICKER_UP_HOUR_DATA = "picker-up-hour-data"
PICKER_DOWN_HOUR_DATA = "picker-down-hour-data"
PICKER_UP_MINUTE_DATA = "picker-up-minute-data"
PICKER_DOWN_MINUTE_DATA = "picker-down-minute-data"
PICKER_SAVE_DATA = "picker-save-data"
NO_ACTION_DATA = "no-action-data"

# reusable keyboard buttons
KEYBOARD_RESTART = InlineKeyboardButton(text="Restart", callback_data=RESTART_DATA)
KEYBOARD_SERVICE_LINE = [
    InlineKeyboardButton(text="Go back", callback_data=GO_BACK_DATA),
    KEYBOARD_RESTART,
]
