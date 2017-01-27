import re

from streamlink.plugin import Plugin
from streamlink.plugin.api import http, validate
from streamlink.stream import HTTPStream, HLSStream

API_URL = "https://www.zhanqi.tv/api/static/v2.1/room/domain/{0}.json"

_url_re = re.compile(r"""
    http(s)?://(www\.)?zhanqi.tv
    /(?P<channel>[^/]+)
""", re.VERBOSE)

_room_schema = validate.Schema(
    {
        "data": validate.any(None, {
            "status": validate.all(
                validate.text,
                validate.transform(int)
            ),
            "videoId": validate.text
        })
    },
    validate.get("data")
)


class Zhanqitv(Plugin):
    @classmethod
    def can_handle_url(self, url):
        return _url_re.match(url)

    def _get_streams(self):
        match = _url_re.match(self.url)
        channel = match.group("channel")

        res = http.get(API_URL.format(channel))
        room = http.json(res, schema=_room_schema)
        if not room:
            self.logger.info("Not a valid room url.")
            return

        if room["status"] != 4:
            self.logger.info("Stream current unavailable.")
            return

        hls_url = "http://dlhls.cdn.zhanqi.tv/zqlive/{room[videoId]}_1024/index.m3u8?Dnion_vsnae={room[videoId]}".format(room=room)
        hls_stream = HLSStream(self.session, hls_url)
        if hls_stream:
            yield "hls", hls_stream

        http_url = "http://wshdl.load.cdn.zhanqi.tv/zqlive/{room[videoId]}.flv?get_url=".format(room=room)
        http_stream = HTTPStream(self.session, http_url)
        if http_stream:
            yield "live", http_stream


__plugin__ = Zhanqitv
