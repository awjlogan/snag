"""
This is a simple mirror for the National Grid Carbon Intensity Forecast API
Use this when you have multiple instances of `snag` running to avoid excess
requests to the NG server.

It will cache responses for a given outward or regional request. These are
lazily updated when required and pruned when unused for a period of time.
"""

import datetime
import sys
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer
from time import sleep
from urllib import request


class Sizzler(BaseHTTPRequestHandler):

    cache: dict[str, tuple[str, bytearray]] = {}

    @staticmethod
    def half_hour_floor(dt: datetime.datetime) -> datetime.datetime:
        """
        Round a datetime down to the last half hour interval
        :param dt: datetime to round down
        :return: datetime rounded down
        """
        mins_mod30: int = dt.minute % 30
        if mins_mod30 or dt.second or dt.microsecond:
            dt = dt - datetime.timedelta(minutes=mins_mod30,
                                         seconds=dt.second,
                                         microseconds=dt.microsecond)
        return dt

    def fetch_ng(self) -> bytearray:
        print(self.path)
        success: bool = False
        attempts: int = 0
        delay: int = 1
        base_url: str = "https://api.carbonintensity.org.uk"
        while not success and attempts < 3:
            attempts += 1
            try:
                page = request.urlopen(f"{base_url}{self.path}")
                success = True
            except urllib.error.HTTPError:
                sleep(delay)
                delay *= 2
                continue

        return page.read()

    def do_GET(self) -> None:
        # Determine the type of request, update the cache if required, then
        # return the response.
        # Request types:
        # 0:    National
        # 1-17  Regional
        # Other Regional by postcode
        print(self.path)
        split_path: list[str] = self.path.split('/')[1:]
        cache_key: str | None = None
        update_reqd: bool = False
        time_now: datetime.datetime = datetime.datetime.now()

        if "fw48h" in self.path:
            if len(split_path) != 3:
                cache_key = split_path[-1]
            else:
                cache_key = '0'

        # Rounding the last updated time up and the current time down, if these
        # are not the same, then the forecast needs to be updated. If the key
        # does not exist, then add to the cache
        try:
            cached_time: str = self.cache[cache_key][0]
            time_last: datetime.datetime = datetime.datetime.fromisoformat(cached_time)
            time_last_down: datetime.datetime = self.half_hour_floor(time_last)
            time_now_down: datetime.datetime = self.half_hour_floor(time_now)
            if time_last_down != time_now_down:
                update_reqd = True
        except KeyError:
            update_reqd = True

        if update_reqd and cache_key:
            self.cache[cache_key] = (time_now.isoformat(),
                                     self.fetch_ng())

        self.send_response(200)
        self.end_headers()

        if cache_key:
            self.wfile.write(self.cache[cache_key][1])
        else:
            self.wfile.write(b"Unknown GET request")


def main() -> None:
    port: int = 8080
    try:
        port = int(sys.argv[2])
    except IndexError:  # no port specified, use default
        pass
    except ValueError as e:
        print(f"Could not convert argument to int: {e}")
        exit(1)

    print(f"Starting sizzler on port {port}")
    server = HTTPServer(("localhost", port), Sizzler)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    server.server_close()


if __name__ == "__main__":
    main()
