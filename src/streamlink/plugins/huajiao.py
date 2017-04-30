import base64
import re
import time
import json

from streamlink.plugin import Plugin
from streamlink.plugin.api import http, validate, useragents
from streamlink.stream import HTTPStream, HLSStream

API_URL = "http://webh.huajiao.com/User/getUserFeeds?fmt=jsonp&uid={0}"
LAPI_URL = "http://g2.live.360.cn/liveplay?channel={0}&sn={1}&_rate=xd&stype={2}&sid={3}&ts={4}"
ROOM_URL = "http://www.huajiao.com/l/{0}"

_url_re = re.compile(r"""
    http(s)?://
    (?:
        (www\.)
    )?
    huajiao.com/
    (?:
        (?P<page>[^/]+)
    )
    (?:
        /
        (?P<channel>[^/&?]+)
    )?
""", re.VERBOSE)

_status_re = re.compile(r'"replay_status"\s*:\s*(\d+),')
_roomid_re = re.compile(r'"relateid"\s*:\s*(\d+),')
_feed_json_re = re.compile(r'^\s*var\s*feed\s*=\s*(?P<feed>{.*})\s*;', re.MULTILINE)

_feed_json_schema = validate.Schema(
    validate.all(
        validate.transform(_feed_json_re.search),
        validate.any(
            None,
            validate.all(
                validate.get('feed'),
                validate.transform(json.loads)
            )
        )
    )
)


class Huajiao(Plugin):
    @classmethod
    def can_handle_url(cls, url):
        return _url_re.match(url)

    def _get_streams(self):
        match = _url_re.match(self.url)
        page = match.group("page")
        channel = match.group("channel")

        http.headers.update({"User-Agent": useragents.CHROME})

        if page == 'user':
            res = http.get(API_URL.format(channel))
            status = _status_re.search(res.text)
            if not status:
                self.logger.info("Stream currently unavailable.")
                return
            elif status.group(1) != '0':
                self.logger.info("Stream currently unavailable.")
                return
            else:
                channel = _roomid_re.search(res.text).group(1)

        feed_json = http.get(ROOM_URL.format(channel), schema=_feed_json_schema)
        if feed_json['feed']['m3u8']:
            yield "live", HLSStream(self.session, feed_json['feed']['m3u8'])
        else:
            channel_sid = feed_json['relay']['channel']
            sn = feed_json['feed']['sn']
            stype = ["flv", "m3u8"]
            sid = int(time.time() * 1000) / 1000.0
            ts = int(time.time())
            for i in range(0, 2, 1):
                encoded_json = http.get(LAPI_URL.format(channel_sid, sn, stype[i], sid, ts)).content
                decoded_json = base64.decodestring(encoded_json[0:3] + encoded_json[6:]).decode('utf-8')
                video_data = json.loads(decoded_json)
                url = video_data['main']
                if '.flv' in url:
                    yield "live", HTTPStream(self.session, url)
                if '.m3u8' in url:
                    yield "live", HLSStream(self.session, url)


__plugin__ = Huajiao
