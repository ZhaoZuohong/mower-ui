from __future__ import annotations

import time
from typing import Optional

from .adb_client import ADBClient
from .minitouch import MiniTouch
from .scrcpy import Scrcpy
from .. import config
from ..log import logger, save_screenshot


class Device(object):
    """ Android Device """

    class Control(object):
        """ Android Device Control """

        def __init__(self, device: Device, client: ADBClient = None, touch_device: str = None) -> None:
            self.device = device
            self.minitouch = None
            self.scrcpy = None

            if config.ADB_CONTROL_CLIENT == 'minitouch':
                self.minitouch = MiniTouch(client, touch_device)
            elif config.ADB_CONTROL_CLIENT == 'scrcpy':
                self.scrcpy = Scrcpy(client)
            else:
                # MiniTouch does not support Android 10+
                if int(client.android_version().split('.')[0]) < 10:
                    self.minitouch = MiniTouch(client, touch_device)
                else:
                    self.scrcpy = Scrcpy(client)

        def tap(self, point: tuple[int, int]) -> None:
            if self.minitouch:
                self.minitouch.tap([point], self.device.display_frames())
            elif self.scrcpy:
                self.scrcpy.tap(point[0], point[1])
            else:
                raise NotImplementedError

        def swipe(self, start: tuple[int, int], end: tuple[int, int], duration: int) -> None:
            if self.minitouch:
                self.minitouch.smooth_swipe(
                    [start, end], self.device.display_frames(), duration=duration)
            elif self.scrcpy:
                duration /= 1000
                self.scrcpy.swipe(start[0], start[1], end[0], end[1], duration)
            else:
                raise NotImplementedError

        def swipe_ext(self, points: list[tuple[int, int]], durations: list[int], up_wait: int) -> None:
            if self.minitouch:
                self.minitouch.smooth_swipe(
                    points, self.device.display_frames(), duration=durations, up_wait=up_wait)
            elif self.scrcpy:
                total = len(durations)
                for idx, (S, E, D) in enumerate(zip(points[:-1], points[1:], durations)):
                    self.scrcpy.swipe(S[0], S[1], E[0], E[1], D / 1000,
                                      up_wait / 1000 if idx == total-1 else 0,
                                      fall=idx == 0, lift=idx == total-1)
            else:
                raise NotImplementedError

    def __init__(self, device_id: str = None, connect: str = None, touch_device: str = None) -> None:
        self.device_id = device_id
        self.connect = connect
        self.touch_device = touch_device
        self.client = None
        self.control = None
        self.start()

    def start(self) -> None:
        self.client = ADBClient(self.device_id, self.connect)
        self.control = Device.Control(self, self.client)

    def run(self, cmd: str) -> Optional[bytes]:
        return self.client.run(cmd)

    def launch(self, app: str) -> None:
        """ launch the application """
        self.run(f'am start -n {app}')

    def send_keyevent(self, keycode: int) -> None:
        """ send a key event """
        logger.debug(f'keyevent: {keycode}')
        command = f'input keyevent {keycode}'
        self.run(command)

    def send_text(self, text: str) -> None:
        """ send a text """
        logger.debug(f'text: {repr(text)}')
        text = text.replace('"', '\\"')
        command = f'input text "{text}"'
        self.run(command)

    def screencap(self, save: bool = False) -> bytes:
        """ get a screencap """
        command = 'screencap -p'
        screencap = self.run(command)
        if save:
            save_screenshot(screencap)
        return screencap

    def current_focus(self) -> str:
        """ detect current focus app """
        command = 'dumpsys window | grep mCurrentFocus'
        line = self.run(command).decode('utf8')
        return line.strip()[:-1].split(' ')[-1]

    def display_frames(self) -> tuple[int, int, int]:
        """ get display frames if in compatibility mode"""
        if not config.MNT_COMPATIBILITY_MODE:
            return None

        command = 'dumpsys window | grep DisplayFrames'
        line = self.run(command).decode('utf8')
        """ eg. DisplayFrames w=1920 h=1080 r=3 """
        res = line.strip().replace('=', ' ').split(' ')
        return int(res[2]), int(res[4]), int(res[6])

    def tap(self, point: tuple[int, int]) -> None:
        """ tap """
        logger.debug(f'tap: {point}')
        self.control.tap(point)

    def swipe(self, start: tuple[int, int], end: tuple[int, int], duration: int = 100) -> None:
        """ swipe """
        logger.debug(f'swipe: {start} -> {end}, duration={duration}')
        self.control.swipe(start, end, duration)

    def swipe_ext(self, points: list[tuple[int, int]], durations: list[int], up_wait: int = 500) -> None:
        """ swipe_ext """
        logger.debug(
            f'swipe_ext: points={points}, durations={durations}, up_wait={up_wait}')
        self.control.swipe_ext(points, durations, up_wait)

    def check_current_focus(self):
        """ check if the application is in the foreground """
        if self.current_focus() != config.APPNAME:
            self.launch(config.APPNAME)
            # wait for app to finish launching
            time.sleep(10)
