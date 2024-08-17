import asyncio
import sys
from io import BytesIO
from pprint import pprint
from typing import Optional, AsyncGenerator
from urllib.parse import urlparse
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


async def get_route_preview(route_url: str):
    loop = asyncio.get_event_loop()
    preview = await loop.run_in_executor(None, opengraph.OpenGraph, route_url)

    pprint(preview, stream=sys.stderr)

    domain = urlparse(route_url).netloc
    if 'strava.com' in domain:
        name, length = preview['description'].split(' Cycling Route. ')[0].split(' is a ')
    elif 'komoot.com' in domain:
        name = preview['title'].split(' | ')[0]
        length = preview['description'].split('Distance: ')[1].split(' | ')[0].replace('\xa0', '')
    else:
        raise Exception('Only komoot and strava routes are supported')

    async with aiohttp.ClientSession() as session:
        url = preview['image']
        async with session.get(url) as resp:
            if resp.status == 200:
                image_data = await resp.read()
            else:
                raise Exception('Failed to fetch image')

    text = f"{name} | {length}"
    image_with_title = await loop.run_in_executor(None, add_title_to_image, image_data, text)
    return InMemoryInputFile(image_with_title)
