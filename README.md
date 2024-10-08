# Announceman

Telegram bot to generate announcements easier with all the links already formatted.

It was created for [@cycling_tbilisi](http://t.me/cycling_tbilisi) community,
but can be modified for other locations and\or activities easily.

Its purpose is to not kill creativity, but to simplify your life when you're lazy
and still want your announcement to contain all important links for newcomers to use.

For now, bot only supports hardcoded dates, times and paces.
You'll need to adjust the code to change them.

## Deployment
### Prerequisites
1. Acquire Bot token from Telegram.
Use [@BotFather](http://t.me/botfather) to create a new bot and save the token for later use
2. Download location data. For Tbilisi you can use
[Tbilisi announceman data](https://github.com/lunrox/announceman_data_tbilisi).
For another location you can create your own repo using the same structure.
3. Create a symlink from your location data into current folder called "announceman_data".
Example (change first argument to where your location data is):
```bash
ln -s ../announceman_data_tbilisi announceman_data
```
### Deploy with docker-compose
1. Set BOT_TOKEN env variable
```bash
export BOT_TOKEN="<put your token here>"
```
2. Build bot image
```bash
docker-compose build
```
3. Deploy bot container
```bash
docker-compose up -d
```

### Route previews
Bot can generate route previews for Strava and Komoot routes and will include
them into announcements.

### Location data update
During first start bot will generate previews for all the routes
and save them in the `announceman_data` folder. If data was changed and previews
need to be updated - remove `.routes_loaded.pickle` file and restart the bot
