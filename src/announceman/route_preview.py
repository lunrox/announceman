from io import BytesIO
from typing import Tuple
from urllib.parse import urlparse
from urllib.request import urlopen

import requests
from PIL import Image, ImageDraw

import opengraph
from bs4 import BeautifulSoup
from pydantic.dataclasses import dataclass


@dataclass
class Route:
    name: str
    length: str
    elevation: str
    link: str
    preview_message: str
    preview_image: bytes
    preview_id: str = None


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


def get_preview_info(route_url) -> Tuple[str, str, str, str]:
    html = urlopen(route_url).read()
    soup = BeautifulSoup(html, 'html.parser')
    link_preview = opengraph.OpenGraph(html=soup)

    domain = urlparse(route_url).netloc
    if 'strava.com' in domain:
        name, length = link_preview['description'].split(' Cycling Route. ')[0].split(' is a ')
        elevation = soup.find_all(**{"class":"Detail_routeStat__7yEdS"})[1].get_text()
    elif 'komoot.com' in domain:
        name = link_preview['title'].split(' | ')[0]
        length = link_preview['description'].split('Distance: ')[1].split(' | ')[0].replace('\xa0', '')
        elevation = soup.find(**{"data-test-id": "t_elevation_up_value"}).get_text().replace('\xa0', '')
    else:
        raise Exception('Only komoot and strava routes are supported')

    return name, length, elevation, link_preview['image']


def load_route(route_url, route_name=None) -> Route:
    if route_name is not None:
        print('loading route', route_name)
    name, length, elevation, img_link = get_preview_info(route_url)
    name = route_name or name

    response = requests.get(img_link)
    if response.status_code != 200:
        raise Exception('Failed to fetch image')

    return Route(
        name=name,
        length=length,
        elevation=elevation,
        link=route_url,
        preview_message=f"[{name}]({route_url})",
        preview_image=add_title_to_image(response.content, f"{name} | {length} | {elevation}"),
    )
