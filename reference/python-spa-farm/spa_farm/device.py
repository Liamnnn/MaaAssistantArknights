"""设备控制：ADB 截图 + minitouch 触控（失败回落 adb input）。

为什么需要 minitouch：卫戍协议的部署是「按住干员 → 持续移动抓起 → 拖到格位 → 松手」，
`adb shell input swipe` 产生的是线性惯性滑动，抓不起干员。minitouch 可以精确控制
down/move/up 与每一步之间的等待，和 MAA 自己的触控实现是同一套思路。

minitouch 二进制直接使用本机 MAA 安装目录里自带的那份（resource/minitouch/<abi>/minitouch），
不额外分发二进制。
"""

from __future__ import annotations

import re
import socket
import subprocess
import time
from pathlib import Path
from typing import Sequence

from .geometry import Point

try:  # pragma: no cover
    import cv2
    import numpy as np
except ImportError:  # pragma: no cover
    cv2 = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]


class DeviceError(RuntimeError):
    pass


class Adb:
    def __init__(self, adb: str = "adb", serial: str | None = None, timeout: float = 20.0) -> None:
        self.adb = adb
        self.serial = serial
        self.timeout = timeout

    def _prefix(self) -> list[str]:
        cmd = [self.adb]
        if self.serial:
            cmd += ["-s", self.serial]
        return cmd

    def run(self, args: Sequence[str], timeout: float | None = None, check: bool = True) -> bytes:
        cmd = [*self._prefix(), *args]
        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout or self.timeout,
            )
        except FileNotFoundError as exc:
            raise DeviceError(f"找不到 adb（{self.adb}）：请安装 platform-tools 或用 --adb 指定路径") from exc
        except subprocess.TimeoutExpired as exc:
            raise DeviceError(f"adb 超时：{' '.join(cmd)}") from exc
        if check and proc.returncode != 0:
            message = proc.stderr.decode("utf-8", "replace").strip() or proc.stdout.decode("utf-8", "replace").strip()
            raise DeviceError(f"adb 失败（{proc.returncode}）：{' '.join(cmd)}\n{message}")
        return proc.stdout

    def text(self, args: Sequence[str], **kwargs) -> str:
        return self.run(args, **kwargs).decode("utf-8", "replace")

    # ---------- 连接 ----------

    @staticmethod
    def list_devices(adb: str = "adb") -> list[str]:
        try:
            out = subprocess.run([adb, "devices"], capture_output=True, timeout=15).stdout.decode("utf-8", "replace")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []
        devices = []
        for line in out.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1] == "device":
                devices.append(parts[0])
        return devices

    def ensure(self) -> None:
        self.run(["get-state"])

    def screen_size(self) -> tuple[int, int]:
        out = self.text(["shell", "wm", "size"])
        override = re.search(r"Override size:\s*(\d+)x(\d+)", out)
        physical = re.search(r"Physical size:\s*(\d+)x(\d+)", out)
        match = override or physical
        if not match:
            raise DeviceError(f"无法读取分辨率：{out.strip()}")
        return int(match.group(1)), int(match.group(2))

    def abi(self) -> str:
        return self.text(["shell", "getprop", "ro.product.cpu.abi"]).strip() or "arm64-v8a"

    def screencap(self) -> "np.ndarray":
        if cv2 is None or np is None:
            raise DeviceError("缺少 opencv/numpy，无法解码截图")
        raw = self.run(["exec-out", "screencap", "-p"], timeout=30)
        if not raw:
            raise DeviceError("截图返回空数据（设备可能掉线）")
        image = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise DeviceError("截图解码失败")
        return image


class Minitouch:
    """minitouch 客户端。协议：`d/m/u` 后跟 `c`(commit)，`w <ms>` 等待。"""

    def __init__(self, adb: Adb, maa_dir: str | Path | None, port: int = 28100) -> None:
        self.adb = adb
        self.maa_dir = Path(maa_dir) if maa_dir else None
        self.port = port
        self.sock: socket.socket | None = None
        self.proc: subprocess.Popen | None = None
        self.max_x = 0
        self.max_y = 0
        self.pressure = 50

    # ---------- 生命周期 ----------

    def _binary(self) -> Path | None:
        if not self.maa_dir:
            return None
        abi = self.adb.abi()
        candidates = [
            self.maa_dir / "resource" / "minitouch" / abi / "minitouch",
            self.maa_dir / "resource" / "minitouch" / abi / "minitouch.so",
        ]
        for path in candidates:
            if path.is_file():
                return path
        return None

    def start(self) -> bool:
        binary = self._binary()
        if binary is None:
            return False
        remote = "/data/local/tmp/minitouch"
        try:
            self.adb.run(["push", str(binary), remote])
            self.adb.run(["shell", "chmod", "755", remote])
            self.proc = subprocess.Popen(
                [*self.adb._prefix(), "shell", remote],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(0.6)
            self.adb.run(["forward", "--remove", f"tcp:{self.port}"], check=False)
            self.adb.run(["forward", f"tcp:{self.port}", "localabstract:minitouch"])
            self.sock = socket.create_connection(("127.0.0.1", self.port), timeout=5)
            self.sock.settimeout(5)
            banner = self._read_banner()
            return banner and self.max_x > 0
        except (DeviceError, OSError):
            self.stop()
            return False

    def _read_banner(self) -> bool:
        assert self.sock is not None
        data = b""
        deadline = time.time() + 5
        while b"$" not in data and time.time() < deadline:
            try:
                chunk = self.sock.recv(4096)
            except socket.timeout:
                break
            if not chunk:
                break
            data += chunk
            if data.count(b"\n") >= 3:
                break
        for line in data.decode("utf-8", "replace").splitlines():
            if line.startswith("$"):
                parts = line[1:].strip().split()
                if len(parts) >= 3:
                    self.max_x, self.max_y, self.pressure = int(parts[0]), int(parts[1]), min(80, int(parts[2]))
        return self.max_x > 0

    def stop(self) -> None:
        try:
            if self.sock:
                self.sock.close()
        except OSError:
            pass
        self.sock = None
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
        self.proc = None
        try:
            self.adb.run(["forward", "--remove", f"tcp:{self.port}"], check=False)
        except DeviceError:
            pass

    # ---------- 指令 ----------

    def _send(self, data: str) -> None:
        if self.sock is None:
            raise DeviceError("minitouch 未连接")
        self.sock.sendall(data.encode("utf-8"))

    def _coords(self, point: Point, screen: tuple[int, int]) -> tuple[int, int]:
        # minitouch 的坐标上限通常等于设备显示分辨率；截图可能被缩放，这里做一次归一化
        if screen[0] != self.max_x or screen[1] != self.max_y:
            return round(point.x * self.max_x / screen[0]), round(point.y * self.max_y / screen[1])
        return point.x, point.y

    def down(self, point: Point, screen: tuple[int, int]) -> None:
        x, y = self._coords(point, screen)
        self._send(f"d 0 {x} {y} {self.pressure}\nc\n")

    def move(self, point: Point, screen: tuple[int, int], settle_ms: int = 16) -> None:
        x, y = self._coords(point, screen)
        self._send(f"m 0 {x} {y} {self.pressure}\nw {settle_ms}\nc\n")

    def up(self, point: Point, screen: tuple[int, int]) -> None:
        x, y = self._coords(point, screen)
        self._send(f"u 0\nc\n")


class Controller:
    """对上层暴露 tap/swipe/drag/screenshot，内部优先 minitouch。"""

    def __init__(self, adb: Adb, maa_dir: str | Path | None, use_minitouch: bool = True) -> None:
        self.adb = adb
        self.screen = adb.screen_size()
        self.minitouch = Minitouch(adb, maa_dir) if use_minitouch else None
        self._mt_ready = False

    def start(self) -> None:
        self.adb.ensure()
        self.screen = self.adb.screen_size()
        # 以截图实际尺寸为准（wm size 在部分模拟器/PC 端会与截图不一致）
        try:
            frame = self.adb.screencap()
            self.screen = (frame.shape[1], frame.shape[0])
        except DeviceError:
            pass
        if self.minitouch is not None:
            self._mt_ready = self.minitouch.start()
        if not self._mt_ready:
            self.minitouch = None

    @property
    def using_minitouch(self) -> bool:
        return self._mt_ready

    def close(self) -> None:
        if self.minitouch is not None:
            self.minitouch.stop()

    def screenshot(self):
        from .vision import Screenshot

        return Screenshot(self.adb.screencap())

    def tap(self, point: Point, settle: float = 0.05) -> None:
        if self._mt_ready and self.minitouch is not None:
            self.minitouch.down(point, self.screen)
            self.minitouch.up(point, self.screen)
        else:
            self.adb.run(["shell", "input", "tap", str(point.x), str(point.y)])
        if settle:
            time.sleep(settle)

    def swipe(self, start: Point, end: Point, duration_ms: int = 300) -> None:
        if self._mt_ready and self.minitouch is not None:
            self.minitouch.down(start, self.screen)
            steps = max(4, duration_ms // 16)
            for i in range(1, steps + 1):
                point = Point(
                    round(start.x + (end.x - start.x) * i / steps),
                    round(start.y + (end.y - start.y) * i / steps),
                )
                self.minitouch.move(point, self.screen, settle_ms=max(8, duration_ms // steps))
            self.minitouch.up(end, self.screen)
        else:
            self.adb.run(
                ["shell", "input", "swipe", str(start.x), str(start.y), str(end.x), str(end.y), str(duration_ms)]
            )

    # ---------- 低层按压（部署时需要中途截图判断可放置格） ----------

    def press(self, point: Point) -> None:
        if self._mt_ready and self.minitouch is not None:
            self.minitouch.down(point, self.screen)

    def move_to(self, point: Point, settle_ms: int = 16) -> None:
        if self._mt_ready and self.minitouch is not None:
            self.minitouch.move(point, self.screen, settle_ms=settle_ms)

    def release(self, point: Point) -> None:
        if self._mt_ready and self.minitouch is not None:
            self.minitouch.up(point, self.screen)

    def drag(self, start: Point, end: Point, hold_ms: int = 300, move_ms: int = 300, steps: int = 8) -> None:
        """按住 → 等待 → 分段移动 → 终点停留 → 松手。部署干员必须用这个。"""
        if not (self._mt_ready and self.minitouch is not None):
            # 回落：input swipe 的持续时间包含按压，先长按再滑只能近似
            self.adb.run(
                ["shell", "input", "swipe", str(start.x), str(start.y), str(end.x), str(end.y), str(max(300, move_ms))]
            )
            return
        self.minitouch.down(start, self.screen)
        time.sleep(hold_ms / 1000)
        per = max(16, move_ms // steps)
        for i in range(1, steps + 1):
            point = Point(
                round(start.x + (end.x - start.x) * i / steps),
                round(start.y + (end.y - start.y) * i / steps),
            )
            self.minitouch.move(point, self.screen, settle_ms=per)
        time.sleep(0.15)
        self.minitouch.up(end, self.screen)
