# photoGPSbot

*Bot for Telegram that receives your photo and returns:*
 - map where the photo was taken (if there are coordinates in your photo)
 - time and date when the photo was taken
 - address (thanks to geopy)
 - number of users with the same camera/smartphone (except you)
 - number of users with the same lens (if there is any)
 - number of users which sent photos from the same country

It supports two languages: English and Russian.
So it can answer you in English or in Russian. You can switch the language anytime from special menu.

User also can see three top charts from menu:
1. List of most popular smartphones/cameras among users of the bot
2. List of most popular lenses among users of the bot
3. List of most popular countries among users of the bot

Lists update not more frequently than in 5 minutes in order not to call database too often.

The bot also has special admin menu to show different statistics, but it is hidden from users.

P.S. You need send photo as a file in order not to lose EXIF.

