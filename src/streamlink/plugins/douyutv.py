import hashlib
import re
import time
import uuid

from requests.adapters import HTTPAdapter

from streamlink.plugin import Plugin
from streamlink.plugin.api import http, validate, useragents
from streamlink.stream import HTTPStream, HLSStream, RTMPStream

#algorithm for https://github.com/spacemeowx2/DouyuHTML5Player/blob/master/src/douyu/blackbox.js
#python version by debugzxcv at https://gist.github.com/debugzxcv/85bb2750d8a5e29803f2686c47dc236b
from streamlink.plugins.douyutv_blackbox import stupidMD5

WAPI_URL = "https://www.douyu.com/swf_api/room/{0}?cdn=&nofan=yes&_t={1}&sign={2}"
LAPI_URL = "https://www.douyu.com/lapi/live/getPlay/{0}"
VAPI_URL = "https://vmobile.douyu.com/video/getInfo?vid={0}"
WAPI_SECRET = "bLFlashflowlad92"
LAPI_SECRET = "a2053899224e8a92974c729dceed1cc99b3d8282"
SHOW_STATUS_ONLINE = 1
SHOW_STATUS_OFFLINE = 2
STREAM_WEIGHTS = {
    "low": 540,
    "medium": 720,
    "source": 1080
}

_url_re = re.compile(r"""
    http(s)?://
    (?:
        (?P<subdomain>.+)
        \.
    )?
    douyu.com/
    (?:
        show/(?P<vid>[^/&?]+)|
        (?P<channel>[^/&?]+)
    )
""", re.VERBOSE)

_room_id_re = re.compile(r'"room_id\\*"\s*:\s*(\d+),')
_room_id_alt_re = re.compile(r'data-room_id="(\d+)"')

_room_id_schema = validate.Schema(
    validate.all(
        validate.transform(_room_id_re.search),
        validate.any(
            None,
            validate.all(
                validate.get(1),
                validate.transform(int)
            )
        )
    )
)

_room_id_alt_schema = validate.Schema(
    validate.all(
        validate.transform(_room_id_alt_re.search),
        validate.any(
            None,
            validate.all(
                validate.get(1),
                validate.transform(int)
            )
        )
    )
)

_room_schema = validate.Schema(
    {
        "data": validate.any(None, {
            "show_status": validate.all(
                validate.text,
                validate.transform(int)
            )
        })
    },
    validate.get("data")
)

_lapi_schema = validate.Schema(
    {
        "data": validate.any(None, {
            "rtmp_url": validate.text,
            "rtmp_live": validate.text
        })
    },
    validate.get("data")
)

_vapi_schema = validate.Schema(
    {
        "data": validate.any(None, {
            "video_url": validate.text
        })
    },
    validate.get("data")
)


class Douyutv(Plugin):
    @classmethod
    def can_handle_url(cls, url):
        return _url_re.match(url)

    @classmethod
    def stream_weight(cls, stream):
        if stream in STREAM_WEIGHTS:
            return STREAM_WEIGHTS[stream], "douyutv"
        return Plugin.stream_weight(stream)

    def _get_room_json(self, channel, rate, ts, did, sign):
        data = {
            "cdn": "ws",#cdns: ["ws", "tct", "ws2", "dl"]
            "rate": rate,
            "tt": ts,
            "did": did,
            "sign": sign
        }
        res = http.post(LAPI_URL.format(channel), data=data)
        room = http.json(res, schema=_lapi_schema)
        return room

    def _get_streams(self):
        match = _url_re.match(self.url)
        subdomain = match.group("subdomain")

        http.verify = False
        http.mount('https://', HTTPAdapter(max_retries=99))

        if subdomain == 'v':
            vid = match.group("vid")
            headers = {
                "User-Agent": useragents.ANDROID,
                "X-Requested-With": "XMLHttpRequest"
            }
            res = http.get(VAPI_URL.format(vid), headers=headers)
            room = http.json(res, schema=_vapi_schema)
            yield "source", HLSStream(self.session, room["video_url"])
            return

        #Thanks to @ximellon for providing method.
        channel = match.group("channel")
        http.headers.update({'User-Agent': useragents.CHROME})
        try:
            channel = int(channel)
        except ValueError:
            channel = http.get(self.url, schema=_room_id_schema)
            if channel == 0:
                channel = http.get(self.url, schema=_room_id_alt_schema)

        ts = int(time.time() / 60)
        sign = hashlib.md5(("{0}{1}{2}".format(channel, WAPI_SECRET, ts)).encode("utf-8")).hexdigest()

        res = http.get(WAPI_URL.format(channel, ts, sign))
        room = http.json(res, schema=_room_schema)
        if not room:
            self.logger.info("Not a valid room url.")
            return

        if room["show_status"] != SHOW_STATUS_ONLINE:
            self.logger.info("Stream currently unavailable.")
            return

        did = uuid.uuid4().hex.upper()
        sign = stupidMD5(("{0}{1}{2}{3}".format(channel, did, LAPI_SECRET, ts)))

        rate = [0, 2, 1]
        quality = ['source', 'medium', 'low']
        for i in range(0, 3, 1):
            room = self._get_room_json(channel, rate[i], ts, did ,sign)
            url = "{room[rtmp_url]}/{room[rtmp_live]}".format(room=room)
            if 'rtmp:' in url:
                stream = RTMPStream(self.session, {
                        "rtmp": url,
                        "live": True
                        })
                yield quality[i], stream
            else:
                yield quality[i], HTTPStream(self.session, url)


__plugin__ = Douyutv
