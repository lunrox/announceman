import asyncio
import sys
from dataclasses import dataclass
from io import BytesIO
from pprint import pprint
from typing import Optional, AsyncGenerator, Tuple
from urllib.parse import urlparse

import requests
from PIL import Image, ImageDraw
from aiogram.types.input_file import InputFile, DEFAULT_CHUNK_SIZE


import aiohttp
import opengraph


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


def add_title_to_image(image_data: bytes, text: str) -> bytes:
    img = Image.open(BytesIO(image_data)).convert('RGB')
    draw = ImageDraw.Draw(img, 'RGB')

    font_size = round(img.height * 0.1)
    text_length = draw.textlength(text, font_size=font_size)
    while text_length > img.width:
        font_size -= 5
        text_length = draw.textlength(text, font_size=font_size)

    x = (img.width - text_length) / 2
    y = round(img.height * 0.85)

    draw.text((x, y), text, fill=(0, 0, 0), font_size=font_size)

    img_io = BytesIO()
    img.save(img_io, 'JPEG')
    return img_io.getvalue()


def get_preview_info(route_url) -> Tuple[str, str, str]:
    link_preview = opengraph.OpenGraph(route_url)

    domain = urlparse(route_url).netloc
    if 'strava.com' in domain:
        name, length = link_preview['description'].split(' Cycling Route. ')[0].split(' is a ')
    elif 'komoot.com' in domain:
        name = link_preview['title'].split(' | ')[0]
        length = link_preview['description'].split('Distance: ')[1].split(' | ')[0].replace('\xa0', '')
    else:
        raise Exception('Only komoot and strava routes are supported')

    return name, length, link_preview['image']


async def get_route_preview(route_url: str):
    loop = asyncio.get_event_loop()
    name, length, image_link = await loop.run_in_executor(None, opengraph.OpenGraph, route_url)

    async with aiohttp.ClientSession() as session:
        async with session.get(image_link) as resp:
            if resp.status == 200:
                image_data = await resp.read()
            else:
                raise Exception('Failed to fetch image')

    preview_text = f"{name} | {length}"
    image_with_title = await loop.run_in_executor(None, add_title_to_image, image_data, preview_text)
    return InMemoryInputFile(image_with_title)


@dataclass
class Route:
    name: str
    description: str
    link: str
    preview_message: str = None
    preview_image: bytes = None


def load_route(route_url, route_name=None) -> Route:
    # todo: add cache for this one
    name, length, img_link = get_preview_info(route_url)
    name = route_name or name

    response = requests.get(img_link)
    if response.status_code != 200:
        raise Exception('Failed to fetch image')
    image_data = response.content

    preview_image = add_title_to_image(image_data, f"{name} | {length}")

    preview_message = f"[{name}]({route_url}) | {length}"
    return Route(name, length, route_url, preview_message, preview_image)
