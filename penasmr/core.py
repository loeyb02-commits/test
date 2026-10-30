"""Device independent motion tracking and distance-driven friction synthesis."""
import math
import random
import time
from array import array
from dataclasses import dataclass

@dataclass(frozen=True)
class Motion:
    speed: float = 0.0
    pressure: float = 0.0
    timestamp: float = 0.0

class Tracker:
    def __init__(self):
        self.previous = None
        self.motion = Motion()

    def update(self, x, y, pressure, contact, now=None):
        now = time.perf_counter() if now is None else now
        speed = 0.0
        if contact and self.previous is not None:
            px, py, pt, was_contact = self.previous
            dt = now - pt
            if was_contact and 0.0001 < dt < 0.1:
                speed = min(8.0, math.hypot(x-px, y-py) / dt)
        self.previous = (x, y, now, contact)
        self.motion = Motion(speed, min(1., max(0., pressure)) if contact else 0., now)

class Friction:
    def __init__(self, rate=48000):
        self.rate = rate
        self.volume = .45
        self.pressure_response = 1.
        self.speed_response = 1.
        self.enabled = True
        self.phase = self.gain = self.low = 0.
        self.last_step = 0.
        self.rng = random.Random()
        # Procedural spatial paper texture, no external samples or sample license.
        self.texture = [self.rng.uniform(-1, 1) for _ in range(65536)]

    def render(self, frames, motion, now=None):
        now = time.perf_counter() if now is None else now
        active = self.enabled and now-motion.timestamp < .035 and motion.speed > .002 and motion.pressure > 0
        speed = motion.speed if active else 0.
        target = self.volume * (.15 + .85 * motion.pressure ** self.pressure_response) * min(1., speed * 8) if active else 0.
        step = min(24., speed * 18 * self.speed_response)
        if active:
            self.last_step = step
        else:
            step = self.last_step
        output = array('f')
        for _ in range(frames):
            self.gain += (target-self.gain) * .025
            self.phase = (self.phase + step) % len(self.texture)
            i = int(self.phase)
            f = self.phase-i
            value = self.texture[i]*(1-f) + self.texture[(i+1) % len(self.texture)]*f
            self.low += .12*(value-self.low)
            # Band-shaped moving spatial texture with weak nonperiodic grain.
            value = (value-self.low)*.8 + self.rng.uniform(-.06,.06)
            if self.gain < 1e-7:
                self.gain = 0.
            output.append(max(-.95, min(.95, value*self.gain)))
        return output.tobytes()
