#!/usr/bin/env python3

import pygame
import sys
import math
import random
import json
import os
import struct
import time
from typing import List, Tuple, Optional, Dict, Any

SCREEN_WIDTH = 1000
SCREEN_HEIGHT = 700
FPS = 60
CELL_SIZE = 20
GRID_COLS = SCREEN_WIDTH // CELL_SIZE 
GRID_ROWS = SCREEN_HEIGHT // CELL_SIZE 

COL_BG         = (10, 10, 25)
COL_GRID       = (30, 60, 120)
COL_SNAKE_HEAD = (0, 255, 120)
COL_SNAKE_BODY = (0, 200, 80)
COL_FOOD       = (255, 50, 50)
COL_WHITE      = (255, 255, 255)
COL_CYAN       = (0, 255, 255)
COL_NEON_GREEN = (0, 255, 120)
COL_DARK_PANEL = (20, 20, 50)
COL_BORDER     = (0, 180, 255)
COL_GOLD       = (255, 215, 0)

POWERUP_COLOURS = {
    "speed":   (255, 255, 0),
    "ghost":   (180, 0, 255),
    "shield":  (0, 120, 255),
    "double":  (255, 215, 0),
    "split":   (255, 100, 200),
}

DIR_UP    = (0, -1)
DIR_DOWN  = (0, 1)
DIR_LEFT  = (-1, 0)
DIR_RIGHT = (1, 0)

DIFFICULTY = {
    "EASY":   (0.7, 12, 0.02),
    "NORMAL": (1.0, 10, 0.04),
    "HARD":   (1.3, 8,  0.06),
    "INSANE": (1.7, 6,  0.10),
}

SAVE_DIR = os.path.join(os.path.expanduser("~"), ".snake_evolution")
SETTINGS_FILE = os.path.join(SAVE_DIR, "settings.json")
HIGHSCORE_FILE = os.path.join(SAVE_DIR, "highscore.txt")
ACHIEVEMENTS_FILE = os.path.join(SAVE_DIR, "achievements.json")

os.makedirs(SAVE_DIR, exist_ok=True)

STATE_MAIN_MENU      = "MAIN_MENU"
STATE_SETTINGS       = "SETTINGS_MENU"
STATE_ACHIEVEMENTS   = "ACHIEVEMENTS_MENU"
STATE_HOW_TO_PLAY    = "HOW_TO_PLAY"
STATE_GAMEPLAY       = "GAMEPLAY"
STATE_PAUSE          = "PAUSE_MENU"
STATE_GAME_OVER      = "GAME_OVER"
STATE_UPGRADE        = "UPGRADE"
STATE_HIGHSCORES     = "HIGHSCORES"

def clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))

def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t

def ease_out_cubic(t: float) -> float:
    return 1.0 - (1.0 - t) ** 3

def ease_in_out_quad(t: float) -> float:
    if t < 0.5:
        return 2 * t * t
    return 1 - (-2 * t + 2) ** 2 / 2

def draw_glow_circle(surface: pygame.Surface, colour: Tuple[int, int, int],
                     center: Tuple[int, int], radius: int, layers: int = 4):
    glow_surf = pygame.Surface((radius * 4, radius * 4), pygame.SRCALPHA)
    for i in range(layers, 0, -1):
        alpha = max(10, 60 // i)
        r = radius + i * 3
        col = (*colour, alpha)
        pygame.draw.circle(glow_surf, col, (radius * 2, radius * 2), r)
    pygame.draw.circle(glow_surf, (*colour, 220), (radius * 2, radius * 2), radius)
    surface.blit(glow_surf, (center[0] - radius * 2, center[1] - radius * 2),
                 special_flags=pygame.BLEND_ADD)

def draw_glow_rect(surface: pygame.Surface, colour: Tuple[int, int, int],
                   rect: pygame.Rect, width: int = 2, layers: int = 3):
    for i in range(layers, 0, -1):
        alpha = max(15, 80 // i)
        expanded = rect.inflate(i * 4, i * 4)
        s = pygame.Surface((expanded.width, expanded.height), pygame.SRCALPHA)
        pygame.draw.rect(s, (*colour, alpha), s.get_rect(), width + i)
        surface.blit(s, expanded.topleft, special_flags=pygame.BLEND_ADD)
    pygame.draw.rect(surface, colour, rect, width)


def draw_rounded_rect(surface: pygame.Surface, colour, rect: pygame.Rect,
                      radius: int = 8, alpha: int = 255):
    s = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    col = (*colour[:3], alpha) if len(colour) == 3 else colour
    pygame.draw.rect(s, col, s.get_rect(), border_radius=radius)
    surface.blit(s, rect.topleft)


def generate_tone(frequency: float = 440.0, duration: float = 0.1,
                  volume: float = 0.3, sample_rate: int = 22050) -> pygame.mixer.Sound:
    n_samples = int(sample_rate * duration)
    buf = bytearray()
    for i in range(n_samples):
        t = i / sample_rate
        env = max(0.0, 1.0 - t / duration) ** 2
        val = math.sin(2.0 * math.pi * frequency * t) * volume * env
        sample = int(clamp(val, -1.0, 1.0) * 32767)
        buf.extend(struct.pack('<h', sample))
    sound = pygame.mixer.Sound(buffer=bytes(buf))
    return sound


def generate_noise_burst(duration: float = 0.05, volume: float = 0.2,
                         sample_rate: int = 22050) -> pygame.mixer.Sound:
    n_samples = int(sample_rate * duration)
    buf = bytearray()
    for i in range(n_samples):
        env = max(0.0, 1.0 - i / n_samples) ** 3
        val = (random.random() * 2 - 1) * volume * env
        sample = int(clamp(val, -1.0, 1.0) * 32767)
        buf.extend(struct.pack('<h', sample))
    return pygame.mixer.Sound(buffer=bytes(buf))

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


class AudioManager:
    def __init__(self):
        self.enabled: bool = True
        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
        except pygame.error:
            self.enabled = False
        self.sounds: Dict[str, pygame.mixer.Sound] = {}
        self.music_volume: float = 0.5
        self.sfx_volume: float = 0.7
        self._sfx_sound: Optional[pygame.mixer.Sound] = None
        self._has_external_music: bool = False
        if self.enabled:
            self._load_external_audio()
            self._generate_sounds()
            if not self._has_external_music:
                self._generate_music()
        self.music_channel: Optional[pygame.mixer.Channel] = None

    def _load_external_audio(self):
        music_path = os.path.join(_SCRIPT_DIR, "music.mp3")
        sfx_path = os.path.join(_SCRIPT_DIR, "sfx.mp3")
        if os.path.isfile(music_path):
            try:
                pygame.mixer.music.load(music_path)
                self._has_external_music = True
            except pygame.error:
                self._has_external_music = False
        if os.path.isfile(sfx_path):
            try:
                self._sfx_sound = pygame.mixer.Sound(sfx_path)
            except pygame.error:
                self._sfx_sound = None

    def _generate_sounds(self):
        self.sounds["hover"] = generate_tone(800, 0.04, 0.15)
        self.sounds["click"] = generate_tone(600, 0.08, 0.25)
        self.sounds["eat"] = generate_tone(880, 0.1, 0.3)
        self.sounds["powerup"] = self._make_powerup_sound()
        self.sounds["evolve"] = self._make_evolve_sound()
        self.sounds["gameover"] = self._make_gameover_sound()

    def _make_powerup_sound(self) -> pygame.mixer.Sound:
        sr = 22050
        duration = 0.3
        n = int(sr * duration)
        buf = bytearray()
        freqs = [440, 554, 659, 880]
        seg = n // len(freqs)
        for idx, freq in enumerate(freqs):
            for i in range(seg):
                t = i / sr
                env = max(0.0, 1.0 - i / seg) ** 1.5
                val = math.sin(2 * math.pi * freq * t) * 0.25 * env
                buf.extend(struct.pack('<h', int(clamp(val, -1, 1) * 32767)))
        return pygame.mixer.Sound(buffer=bytes(buf))

    def _make_evolve_sound(self) -> pygame.mixer.Sound:
        sr = 22050
        duration = 0.6
        n = int(sr * duration)
        buf = bytearray()
        for i in range(n):
            t = i / sr
            freq = 300 + 600 * (t / duration)
            env = max(0.0, 1.0 - t / duration)
            val = math.sin(2 * math.pi * freq * t) * 0.3 * env
            buf.extend(struct.pack('<h', int(clamp(val, -1, 1) * 32767)))
        return pygame.mixer.Sound(buffer=bytes(buf))

    def _make_gameover_sound(self) -> pygame.mixer.Sound:
        sr = 22050
        duration = 0.8
        n = int(sr * duration)
        buf = bytearray()
        for i in range(n):
            t = i / sr
            freq = 600 - 400 * (t / duration)
            env = max(0.0, 1.0 - t / duration) ** 2
            val = math.sin(2 * math.pi * freq * t) * 0.3 * env
            buf.extend(struct.pack('<h', int(clamp(val, -1, 1) * 32767)))
        return pygame.mixer.Sound(buffer=bytes(buf))

    def _generate_music(self):
        sr = 22050
        bpm = 120
        beat = 60.0 / bpm
        bars = 4
        duration = beat * 4 * bars
        n = int(sr * duration)
        buf = bytearray()
        bass_notes = [110, 110, 146.83, 130.81] * bars
        note_len = n // len(bass_notes)
        for note_idx, freq in enumerate(bass_notes):
            for i in range(note_len):
                t = i / sr
                env = max(0.0, 1.0 - (i / note_len)) ** 1.2
                val = (math.sin(2 * math.pi * freq * t) * 0.15 +
                       math.sin(2 * math.pi * freq * 2 * t) * 0.05) * env
                sample = int(clamp(val, -1, 1) * 32767)
                buf.extend(struct.pack('<h', sample))
        self._music_sound = pygame.mixer.Sound(buffer=bytes(buf))

    def play_sound(self, name: str):
        if not self.enabled:
            return
        if self._sfx_sound is not None:
            self._sfx_sound.set_volume(self.sfx_volume)
            self._sfx_sound.play()
            return
        if name in self.sounds:
            s = self.sounds[name]
            s.set_volume(self.sfx_volume)
            s.play()

    def start_music(self):
        if not self.enabled:
            return
        if self._has_external_music:
            pygame.mixer.music.set_volume(self.music_volume * 0.6)
            pygame.mixer.music.play(loops=-1)
        else:
            self._music_sound.set_volume(self.music_volume * 0.4)
            self.music_channel = self._music_sound.play(loops=-1)

    def stop_music(self):
        if not self.enabled:
            return
        if self._has_external_music:
            pygame.mixer.music.stop()
        elif self.music_channel:
            self.music_channel.stop()

    def update_volumes(self, music_vol: float, sfx_vol: float):
        self.music_volume = music_vol
        self.sfx_volume = sfx_vol
        if not self.enabled:
            return
        if self._has_external_music:
            pygame.mixer.music.set_volume(self.music_volume * 0.6)
        elif self.music_channel:
            self._music_sound.set_volume(self.music_volume * 0.4)

class SettingsManager:
    DEFAULTS: Dict[str, Any] = {
        "music_volume": 50,
        "sfx_volume": 70,
        "screen_shake": True,
        "particle_density": "MEDIUM",
        "difficulty": "NORMAL",
    }

    def __init__(self):
        self.data: Dict[str, Any] = dict(self.DEFAULTS)
        self.load()

    def load(self):
        try:
            with open(SETTINGS_FILE, "r") as f:
                saved = json.load(f)
                self.data.update(saved)
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def save(self):
        with open(SETTINGS_FILE, "w") as f:
            json.dump(self.data, f, indent=2)

    def get(self, key: str) -> Any:
        return self.data.get(key, self.DEFAULTS.get(key))

    def set(self, key: str, value: Any):
        self.data[key] = value

    @property
    def particle_multiplier(self) -> float:
        d = {"LOW": 0.4, "MEDIUM": 1.0, "HIGH": 2.0}
        return d.get(self.data["particle_density"], 1.0)

    @property
    def difficulty_tuple(self) -> Tuple[float, float, float]:
        return DIFFICULTY.get(self.data["difficulty"], DIFFICULTY["NORMAL"])

class HighScoreManager:
    def __init__(self):
        self.scores: List[int] = []
        self.load()

    def load(self):
        try:
            with open(HIGHSCORE_FILE, "r") as f:
                self.scores = [int(line.strip()) for line in f if line.strip().isdigit()]
        except FileNotFoundError:
            self.scores = []
        self.scores.sort(reverse=True)
        self.scores = self.scores[:10]

    def save(self):
        with open(HIGHSCORE_FILE, "w") as f:
            for s in self.scores:
                f.write(f"{s}\n")

    def add(self, score: int):
        self.scores.append(score)
        self.scores.sort(reverse=True)
        self.scores = self.scores[:10]
        self.save()

    @property
    def best(self) -> int:
        return self.scores[0] if self.scores else 0

ACHIEVEMENT_DEFS: List[Dict[str, str]] = [
    {"id": "first_meal",    "name": "FIRST MEAL",       "desc": "Eat your first food."},
    {"id": "growing_fast",  "name": "GROWING FAST",     "desc": "Reach snake length 15."},
    {"id": "unstoppable",   "name": "UNSTOPPABLE",      "desc": "Reach score 1000."},
    {"id": "ghost_master",  "name": "GHOST MASTER",     "desc": "Use Ghost Mode 5 times."},
    {"id": "survivor",      "name": "SURVIVOR",         "desc": "Survive for 5 minutes."},
    {"id": "speed_demon",   "name": "SPEED DEMON",      "desc": "Reach maximum snake speed."},
    {"id": "evolution_master", "name": "EVOLUTION MASTER", "desc": "Trigger 10 evolution events."},
]


class AchievementNotification:
    def __init__(self, name: str):
        self.name = name
        self.timer: float = 0.0
        self.duration: float = 3.0
        self.y_offset: float = -60.0

    @property
    def alive(self) -> bool:
        return self.timer < self.duration

    def update(self, dt: float):
        self.timer += dt
        if self.timer < 0.4:
            self.y_offset = lerp(-60, 10, ease_out_cubic(self.timer / 0.4))
        elif self.timer > self.duration - 0.4:
            t = (self.timer - (self.duration - 0.4)) / 0.4
            self.y_offset = lerp(10, -60, t)

    def draw(self, surface: pygame.Surface, index: int):
        y = int(self.y_offset) + index * 55
        rect = pygame.Rect(SCREEN_WIDTH - 310, y, 300, 45)
        draw_rounded_rect(surface, (10, 10, 40), rect, radius=8, alpha=220)
        draw_glow_rect(surface, COL_NEON_GREEN, rect, width=1, layers=2)
        font = pygame.font.SysFont("consolas", 16, bold=True)
        txt = font.render(f"UNLOCKED: {self.name}", True, COL_NEON_GREEN)
        surface.blit(txt, (rect.x + 10, rect.y + 13))

class AchievementManager:
    def __init__(self):
        self.unlocked: Dict[str, bool] = {a["id"]: False for a in ACHIEVEMENT_DEFS}
        self.notifications: List[AchievementNotification] = []
        self.ghost_uses: int = 0
        self.evolution_count: int = 0
        self.load()

    def load(self):
        try:
            with open(ACHIEVEMENTS_FILE, "r") as f:
                saved = json.load(f)
                for k, v in saved.items():
                    if k in self.unlocked:
                        self.unlocked[k] = v
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def save(self):
        with open(ACHIEVEMENTS_FILE, "w") as f:
            json.dump(self.unlocked, f, indent=2)

    def unlock(self, ach_id: str):
        if ach_id in self.unlocked and not self.unlocked[ach_id]:
            self.unlocked[ach_id] = True
            name = next((a["name"] for a in ACHIEVEMENT_DEFS if a["id"] == ach_id), ach_id)
            self.notifications.append(AchievementNotification(name))
            self.save()

    def check(self, score: int, length: int, speed: float, survive_time: float):
        if length > 0:
            self.unlock("first_meal")
        if length >= 15:
            self.unlock("growing_fast")
        if score >= 1000:
            self.unlock("unstoppable")
        if self.ghost_uses >= 5:
            self.unlock("ghost_master")
        if survive_time >= 300:
            self.unlock("survivor")
        if speed >= 20:
            self.unlock("speed_demon")
        if self.evolution_count >= 10:
            self.unlock("evolution_master")

    def update(self, dt: float):
        for n in self.notifications:
            n.update(dt)
        self.notifications = [n for n in self.notifications if n.alive]

    def draw(self, surface: pygame.Surface):
        for i, n in enumerate(self.notifications):
            n.draw(surface, i)

class Particle:
    __slots__ = ("x", "y", "vx", "vy", "colour", "size", "life", "max_life", "gravity")

    def __init__(self, x: float, y: float, vx: float, vy: float,
                 colour: Tuple[int, int, int], size: float = 3.0,
                 life: float = 1.0, gravity: float = 0.0):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.colour = colour
        self.size = size
        self.life = life
        self.max_life = life
        self.gravity = gravity

    @property
    def alive(self) -> bool:
        return self.life > 0

    def update(self, dt: float):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.vy += self.gravity * dt
        self.life -= dt

    def draw(self, surface: pygame.Surface, ox: int = 0, oy: int = 0):
        if self.life <= 0:
            return
        ratio = max(0.0, self.life / self.max_life)
        alpha = int(255 * ratio)
        r = max(1, int(self.size * ratio))
        s = pygame.Surface((r * 4, r * 4), pygame.SRCALPHA)
        col = (*self.colour, alpha)
        pygame.draw.circle(s, col, (r * 2, r * 2), r)
        glow_col = (*self.colour, alpha // 3)
        pygame.draw.circle(s, glow_col, (r * 2, r * 2), r * 2)
        surface.blit(s, (int(self.x) - r * 2 + ox, int(self.y) - r * 2 + oy),
                     special_flags=pygame.BLEND_ADD)


class ParticleSystem:
    def __init__(self, multiplier: float = 1.0):
        self.particles: List[Particle] = []
        self.multiplier = multiplier

    def emit(self, x: float, y: float, colour: Tuple[int, int, int],
             count: int = 10, speed: float = 100, life: float = 0.8,
             size: float = 3.0, gravity: float = 0.0):
        actual = max(1, int(count * self.multiplier))
        for _ in range(actual):
            angle = random.uniform(0, math.pi * 2)
            spd = random.uniform(speed * 0.3, speed)
            vx = math.cos(angle) * spd
            vy = math.sin(angle) * spd
            lt = random.uniform(life * 0.5, life)
            sz = random.uniform(size * 0.5, size)
            self.particles.append(Particle(x, y, vx, vy, colour, sz, lt, gravity))

    def emit_trail(self, x: float, y: float, colour: Tuple[int, int, int]):
        if random.random() > self.multiplier * 0.5:
            return
        vx = random.uniform(-20, 20)
        vy = random.uniform(-20, 20)
        self.particles.append(Particle(x, y, vx, vy, colour, 2.0, 0.4))

    def update(self, dt: float):
        for p in self.particles:
            p.update(dt)
        self.particles = [p for p in self.particles if p.alive]

    def draw(self, surface: pygame.Surface, ox: int = 0, oy: int = 0):
        for p in self.particles:
            p.draw(surface, ox, oy)

class BackgroundEffect:
    def __init__(self):
        self.grid_offset: float = 0.0
        self.bg_particles: List[Dict[str, float]] = []
        for _ in range(40):
            self.bg_particles.append({
                "x": random.uniform(0, SCREEN_WIDTH),
                "y": random.uniform(0, SCREEN_HEIGHT),
                "vx": random.uniform(-15, 15),
                "vy": random.uniform(-15, 15),
                "size": random.uniform(1, 3),
                "alpha": random.uniform(30, 100),
            })

    def update(self, dt: float):
        self.grid_offset = (self.grid_offset + 15 * dt) % CELL_SIZE
        for p in self.bg_particles:
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            if p["x"] < 0:
                p["x"] = SCREEN_WIDTH
            elif p["x"] > SCREEN_WIDTH:
                p["x"] = 0
            if p["y"] < 0:
                p["y"] = SCREEN_HEIGHT
            elif p["y"] > SCREEN_HEIGHT:
                p["y"] = 0

    def draw(self, surface: pygame.Surface):
        surface.fill(COL_BG)
        offset = int(self.grid_offset)
        for x in range(0, SCREEN_WIDTH + CELL_SIZE, CELL_SIZE):
            pygame.draw.line(surface, COL_GRID, (x, 0), (x, SCREEN_HEIGHT), 1)
        for y in range(0, SCREEN_HEIGHT + CELL_SIZE, CELL_SIZE):
            pygame.draw.line(surface, COL_GRID, (0, y + offset), (SCREEN_WIDTH, y + offset), 1)
        for p in self.bg_particles:
            s = pygame.Surface((int(p["size"] * 4), int(p["size"] * 4)), pygame.SRCALPHA)
            col = (100, 180, 255, int(p["alpha"]))
            pygame.draw.circle(s, col, (int(p["size"] * 2), int(p["size"] * 2)), int(p["size"]))
            surface.blit(s, (int(p["x"]) - int(p["size"] * 2),
                             int(p["y"]) - int(p["size"] * 2)),
                         special_flags=pygame.BLEND_ADD)

class Button:
    def __init__(self, text: str, x: int, y: int, w: int = 300, h: int = 60,
                 font_size: int = 26):
        self.text = text
        self.base_rect = pygame.Rect(x - w // 2, y - h // 2, w, h)
        self.rect = self.base_rect.copy()
        self.font = pygame.font.SysFont("consolas", font_size, bold=True)
        self.hovered = False
        self.clicked = False
        self.click_timer: float = 0.0
        self.hover_scale: float = 1.0

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.clicked = True
                self.click_timer = 0.15
                return True
        return False

    def update(self, dt: float, mouse_pos: Tuple[int, int]):
        self.hovered = self.rect.collidepoint(mouse_pos)
        target = 1.08 if self.hovered else 1.0
        self.hover_scale = lerp(self.hover_scale, target, dt * 10)
        if self.click_timer > 0:
            self.click_timer -= dt
            if self.click_timer <= 0:
                self.clicked = False
        w = int(self.base_rect.width * self.hover_scale)
        h = int(self.base_rect.height * self.hover_scale)
        self.rect = pygame.Rect(self.base_rect.centerx - w // 2,
                                self.base_rect.centery - h // 2, w, h)

    def draw(self, surface: pygame.Surface):
        draw_rounded_rect(surface, COL_DARK_PANEL, self.rect, radius=10, alpha=200)
        border_col = COL_NEON_GREEN if self.hovered else COL_BORDER
        if self.clicked:
            border_col = COL_WHITE
        draw_glow_rect(surface, border_col, self.rect, width=2,
                       layers=4 if self.hovered else 2)
        txt = self.font.render(self.text, True, COL_WHITE)
        surface.blit(txt, (self.rect.centerx - txt.get_width() // 2,
                           self.rect.centery - txt.get_height() // 2))

class Slider:
    def __init__(self, x: int, y: int, w: int, value: int = 50,
                 label: str = ""):
        self.rect = pygame.Rect(x, y, w, 30)
        self.value = value
        self.label = label
        self.dragging = False
        self.font = pygame.font.SysFont("consolas", 18)

    def handle_event(self, event: pygame.event.Event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.inflate(10, 20).collidepoint(event.pos):
                self.dragging = True
                self._update_value(event.pos[0])
        elif event.type == pygame.MOUSEBUTTONUP:
            self.dragging = False
        elif event.type == pygame.MOUSEMOTION and self.dragging:
            self._update_value(event.pos[0])

    def _update_value(self, mx: int):
        ratio = (mx - self.rect.x) / self.rect.width
        self.value = int(clamp(ratio * 100, 0, 100))

    def draw(self, surface: pygame.Surface):
        lbl = self.font.render(f"{self.label}: {self.value}", True, COL_WHITE)
        surface.blit(lbl, (self.rect.x, self.rect.y - 22))
        pygame.draw.rect(surface, (40, 40, 80), self.rect, border_radius=5)
        fill_w = int(self.rect.width * self.value / 100)
        fill_rect = pygame.Rect(self.rect.x, self.rect.y, fill_w, self.rect.height)
        pygame.draw.rect(surface, COL_NEON_GREEN, fill_rect, border_radius=5)
        knob_x = self.rect.x + fill_w
        pygame.draw.circle(surface, COL_WHITE, (knob_x, self.rect.centery), 10)

class ScorePopup:
    def __init__(self, x: int, y: int, value: int, colour: Tuple[int, int, int] = COL_WHITE):
        self.x = x
        self.y = float(y)
        self.value = value
        self.colour = colour
        self.timer: float = 0.0
        self.duration: float = 1.0

    @property
    def alive(self) -> bool:
        return self.timer < self.duration

    def update(self, dt: float):
        self.timer += dt
        self.y -= 40 * dt

    def draw(self, surface: pygame.Surface):
        if not self.alive:
            return
        alpha = int(255 * (1.0 - self.timer / self.duration))
        font = pygame.font.SysFont("consolas", 20, bold=True)
        txt = font.render(f"+{self.value}", True, self.colour)
        txt.set_alpha(alpha)
        surface.blit(txt, (self.x, int(self.y)))

class Snake:
    def __init__(self, start_x: int = 10, start_y: int = 17):
        self.segments: List[Tuple[int, int]] = []
        for i in range(4):
            self.segments.append((start_x - i, start_y))
        self.direction: Tuple[int, int] = DIR_RIGHT
        self.next_direction: Tuple[int, int] = DIR_RIGHT
        self.grow_pending: int = 0
        self.base_speed: float = 8.0 
        self.speed: float = self.base_speed
        self.move_timer: float = 0.0
        self.alive: bool = True

        self.speed_boost_timer: float = 0.0
        self.ghost_timer: float = 0.0
        self.shield_active: bool = False
        self.double_score_timer: float = 0.0
        self.split_timer: float = 0.0
        self.split_segments: List[Tuple[int, int]] = []

        self.head_scale: float = 1.0
        self.trail_colour: Tuple[int, int, int] = COL_SNAKE_HEAD

    @property
    def head(self) -> Tuple[int, int]:
        return self.segments[0]

    @property
    def length(self) -> int:
        return len(self.segments)

    def set_direction(self, d: Tuple[int, int]):
        if (d[0] + self.direction[0] == 0 and d[1] + self.direction[1] == 0):
            return
        self.next_direction = d

    def update(self, dt: float) -> bool:
        if not self.alive:
            return False

        if self.speed_boost_timer > 0:
            self.speed_boost_timer -= dt
            self.speed = self.base_speed * 1.5
            if self.speed_boost_timer <= 0:
                self.speed = self.base_speed
        else:
            self.speed = self.base_speed

        if self.ghost_timer > 0:
            self.ghost_timer -= dt
        if self.double_score_timer > 0:
            self.double_score_timer -= dt
        if self.split_timer > 0:
            self.split_timer -= dt
            if self.split_timer <= 0:
                self.split_segments.clear()

        self.head_scale = lerp(self.head_scale, 1.0, dt * 8)

        self.move_timer += dt
        interval = 1.0 / self.speed
        if self.move_timer >= interval:
            self.move_timer -= interval
            self.direction = self.next_direction
            self._step()
            return True
        return False

    def _step(self):
        hx, hy = self.head
        nx = hx + self.direction[0]
        ny = hy + self.direction[1]

        if self.ghost_timer > 0:
            nx = nx % GRID_COLS
            ny = ny % GRID_ROWS

        self.segments.insert(0, (nx, ny))
        if self.grow_pending > 0:
            self.grow_pending -= 1
        else:
            self.segments.pop()

        if self.split_timer > 0:
            mirror = [(GRID_COLS - 1 - sx, sy) for sx, sy in self.segments]
            self.split_segments = mirror

    def grow(self, amount: int = 1):
        self.grow_pending += amount

    def check_wall_collision(self) -> bool:
        if self.ghost_timer > 0:
            return False
        hx, hy = self.head
        return hx < 0 or hx >= GRID_COLS or hy < 0 or hy >= GRID_ROWS

    def check_self_collision(self) -> bool:
        return self.head in self.segments[1:]

    def apply_powerup(self, ptype: str):
        if ptype == "speed":
            self.speed_boost_timer = 6.0
        elif ptype == "ghost":
            self.ghost_timer = 5.0
        elif ptype == "shield":
            self.shield_active = True
        elif ptype == "double":
            self.double_score_timer = 8.0
        elif ptype == "split":
            self.split_timer = 5.0

    def draw(self, surface: pygame.Surface, particles: ParticleSystem,
             ox: int = 0, oy: int = 0):
        total = len(self.segments)
        for i, (sx, sy) in enumerate(reversed(self.segments)):
            ratio = 1.0 - (i / max(1, total))
            g = int(lerp(80, 255, ratio))
            col = (0, g, int(lerp(40, 120, ratio)))
            alpha = 120 if self.ghost_timer > 0 else 255
            shrink = int(lerp(2, 0, ratio))
            rect = pygame.Rect(sx * CELL_SIZE + shrink + ox,
                               sy * CELL_SIZE + shrink + oy,
                               CELL_SIZE - shrink * 2, CELL_SIZE - shrink * 2)
            s = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            pygame.draw.rect(s, (*col, alpha), s.get_rect(), border_radius=5)
            surface.blit(s, rect.topleft)

            if self.speed_boost_timer > 0 and i == total - 1:
                particles.emit_trail(
                    sx * CELL_SIZE + CELL_SIZE // 2,
                    sy * CELL_SIZE + CELL_SIZE // 2,
                    COL_SNAKE_HEAD)

        hx, hy = self.head
        head_center = (hx * CELL_SIZE + CELL_SIZE // 2 + ox,
                       hy * CELL_SIZE + CELL_SIZE // 2 + oy)
        head_r = int(CELL_SIZE // 2 * self.head_scale)
        draw_glow_circle(surface, COL_SNAKE_HEAD, head_center, head_r, layers=5)

        if self.shield_active:
            draw_glow_circle(surface, (0, 120, 255), head_center, head_r + 4, layers=3)

        if self.split_timer > 0 and self.split_segments:
            for sx, sy in self.split_segments:
                rect = pygame.Rect(sx * CELL_SIZE + 2 + ox,
                                   sy * CELL_SIZE + 2 + oy,
                                   CELL_SIZE - 4, CELL_SIZE - 4)
                s = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
                pygame.draw.rect(s, (255, 100, 200, 120), s.get_rect(), border_radius=4)
                surface.blit(s, rect.topleft)

class Food:
    def __init__(self):
        self.pos: Tuple[int, int] = (0, 0)
        self.pulse: float = 0.0
        self.respawn(set())

    def respawn(self, occupied: set):
        while True:
            x = random.randint(0, GRID_COLS - 1)
            y = random.randint(0, GRID_ROWS - 1)
            if (x, y) not in occupied:
                self.pos = (x, y)
                break

    def update(self, dt: float):
        self.pulse += dt * 4
        if self.pulse > math.pi * 2:
            self.pulse -= math.pi * 2

    def draw(self, surface: pygame.Surface, ox: int = 0, oy: int = 0):
        cx = self.pos[0] * CELL_SIZE + CELL_SIZE // 2 + ox
        cy = self.pos[1] * CELL_SIZE + CELL_SIZE // 2 + oy
        r = 6 + int(2 * math.sin(self.pulse))
        draw_glow_circle(surface, COL_FOOD, (cx, cy), r, layers=4)

class PowerUpFood:
    def __init__(self, ptype: str, pos: Tuple[int, int]):
        self.ptype = ptype
        self.pos = pos
        self.colour = POWERUP_COLOURS.get(ptype, COL_WHITE)
        self.pulse: float = 0.0
        self.lifetime: float = 6.0  
        self.spawn_anim: float = 0.0 

    @property
    def alive(self) -> bool:
        return self.lifetime > 0

    def update(self, dt: float):
        self.pulse += dt * 3
        self.lifetime -= dt
        self.spawn_anim = min(1.0, self.spawn_anim + dt * 3)

    def draw(self, surface: pygame.Surface, ox: int = 0, oy: int = 0):
        if not self.alive:
            return
        if self.lifetime < 2.0 and int(self.lifetime * 6) % 2 == 0:
            return 
        cx = self.pos[0] * CELL_SIZE + CELL_SIZE // 2 + ox
        cy = self.pos[1] * CELL_SIZE + CELL_SIZE // 2 + oy
        scale = ease_out_cubic(self.spawn_anim)
        r = int((7 + 3 * math.sin(self.pulse)) * scale)
        draw_glow_circle(surface, self.colour, (cx, cy), r, layers=5)

class Obstacle:
    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y
        self.alpha: float = 0.0

    @property
    def pos(self) -> Tuple[int, int]:
        return (self.x, self.y)

    def update(self, dt: float):
        self.alpha = min(1.0, self.alpha + dt * 2)

    def draw(self, surface: pygame.Surface, ox: int = 0, oy: int = 0):
        a = int(self.alpha * 200)
        rect = pygame.Rect(self.x * CELL_SIZE + ox, self.y * CELL_SIZE + oy,
                           CELL_SIZE, CELL_SIZE)
        s = pygame.Surface((CELL_SIZE, CELL_SIZE), pygame.SRCALPHA)
        pygame.draw.rect(s, (80, 0, 120, a), s.get_rect(), border_radius=3)
        surface.blit(s, rect.topleft)
        if self.alpha > 0.5:
            draw_glow_rect(surface, (120, 0, 200), rect, width=1, layers=2)

class ScreenShake:
    def __init__(self):
        self.intensity: float = 0.0
        self.offset_x: float = 0.0
        self.offset_y: float = 0.0

    def trigger(self, intensity: float = 5.0):
        self.intensity = intensity

    def update(self, dt: float):
        if self.intensity > 0.1:
            self.offset_x = random.uniform(-self.intensity, self.intensity)
            self.offset_y = random.uniform(-self.intensity, self.intensity)
            self.intensity *= 0.85
        else:
            self.intensity = 0
            self.offset_x = 0
            self.offset_y = 0

    @property
    def offset(self) -> Tuple[int, int]:
        return (int(self.offset_x), int(self.offset_y))

class GameState:
    def __init__(self, game: "Game"):
        self.game = game

    def handle_input(self, events: List[pygame.event.Event]):
        pass

    def update(self, dt: float):
        pass

    def draw(self, surface: pygame.Surface):
        pass

class MainMenuState(GameState):
    def __init__(self, game: "Game"):
        super().__init__(game)
        cx = SCREEN_WIDTH // 2
        self.buttons = [
            Button("START GAME", cx, 320),
            Button("HOW TO PLAY", cx, 400),
            Button("HIGH SCORES", cx, 480),
            Button("ACHIEVEMENTS", cx, 560),
            Button("SETTINGS", cx, 640),
        ]
        self.bg = BackgroundEffect()
        self.title_glow: float = 0.0

    def handle_input(self, events: List[pygame.event.Event]):
        for event in events:
            if event.type == pygame.QUIT:
                self.game.running = False
            for i, btn in enumerate(self.buttons):
                if btn.handle_event(event):
                    self.game.audio.play_sound("click")
                    if i == 0:
                        self.game.change_state(STATE_GAMEPLAY)
                    elif i == 1:
                        self.game.change_state(STATE_HOW_TO_PLAY)
                    elif i == 2:
                        self.game.change_state(STATE_HIGHSCORES)
                    elif i == 3:
                        self.game.change_state(STATE_ACHIEVEMENTS)
                    elif i == 4:
                        self.game.change_state(STATE_SETTINGS)

    def update(self, dt: float):
        self.bg.update(dt)
        self.title_glow += dt * 2
        mouse = pygame.mouse.get_pos()
        for btn in self.buttons:
            old_hover = btn.hovered
            btn.update(dt, mouse)
            if btn.hovered and not old_hover:
                self.game.audio.play_sound("hover")

    def draw(self, surface: pygame.Surface):
        self.bg.draw(surface)

        title_font = pygame.font.SysFont("consolas", 72, bold=True)
        title_col = (0, 0, 0)
        title_surf = title_font.render("SNAKE EVOLUTION", True, title_col)
        tx = SCREEN_WIDTH // 2 - title_surf.get_width() // 2
        ty = 120

        glow_val = int(180 + 75 * math.sin(self.title_glow))
        glow_c_raw = (0, glow_val, int(glow_val * 0.5))
        glow_s = pygame.Surface((title_surf.get_width() + 40, title_surf.get_height() + 40),
                                pygame.SRCALPHA)
        pygame.draw.rect(glow_s, (*glow_c_raw, 40), glow_s.get_rect(), border_radius=15)
        surface.blit(glow_s, (tx - 20, ty - 20), special_flags=pygame.BLEND_ADD)
        surface.blit(title_surf, (tx, ty))

        sub_font = pygame.font.SysFont("consolas", 18)
        sub = sub_font.render("Eat. Evolve. Survive.", True, (100, 200, 255))
        surface.blit(sub, (SCREEN_WIDTH // 2 - sub.get_width() // 2, ty + 80))

        for btn in self.buttons:
            btn.draw(surface)

class HowToPlayState(GameState):
    def __init__(self, game: "Game"):
        super().__init__(game)
        self.bg = BackgroundEffect()
        self.back_btn = Button("BACK", SCREEN_WIDTH // 2, 640)
        self.lines = [
            "CONTROLS:",
            "",
            "  Arrow Keys / WASD  -  Move snake",
            "  ESC                -  Pause game",
            "  Space              -  Activate ability",
            "",
            "GOAL:",
            "  Eat food to grow and score points.",
            "  Every 5 foods triggers an EVOLUTION event.",
            "  Collect power-ups for special abilities!",
            "",
            "POWER-UPS:",
            "  [Yellow]  Speed Boost   - Move 50% faster",
            "  [Purple]  Ghost Mode    - Pass through walls",
            "  [Blue]    Shield        - Survive one self-collision",
            "  [Gold]    Double Score   - 2x points",
            "  [Pink]    Split Body    - Mirror snake",
        ]

    def handle_input(self, events: List[pygame.event.Event]):
        for event in events:
            if event.type == pygame.QUIT:
                self.game.running = False
            if self.back_btn.handle_event(event):
                self.game.audio.play_sound("click")
                self.game.change_state(STATE_MAIN_MENU)
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.game.change_state(STATE_MAIN_MENU)

    def update(self, dt: float):
        self.bg.update(dt)
        self.back_btn.update(dt, pygame.mouse.get_pos())

    def draw(self, surface: pygame.Surface):
        self.bg.draw(surface)
        font_title = pygame.font.SysFont("consolas", 48, bold=True)
        t = font_title.render("HOW TO PLAY", True, COL_CYAN)
        surface.blit(t, (SCREEN_WIDTH // 2 - t.get_width() // 2, 40))

        font = pygame.font.SysFont("consolas", 18)
        y = 120
        powerup_colors = {
            "[Yellow]": (255, 255, 0),
            "[Purple]": (180, 0, 255),
            "[Blue]": (0, 120, 255),
            "[Gold]": (255, 215, 0),
            "[Pink]": (255, 100, 200),
        }
        for line in self.lines:
            col = COL_WHITE
            for tag, c in powerup_colors.items():
                if tag in line:
                    col = c
                    break
            txt = font.render(line, True, col)
            surface.blit(txt, (120, y))
            y += 28

        self.back_btn.draw(surface)

class HighScoresState(GameState):
    def __init__(self, game: "Game"):
        super().__init__(game)
        self.bg = BackgroundEffect()
        self.back_btn = Button("BACK", SCREEN_WIDTH // 2, 640)

    def handle_input(self, events: List[pygame.event.Event]):
        for event in events:
            if event.type == pygame.QUIT:
                self.game.running = False
            if self.back_btn.handle_event(event):
                self.game.audio.play_sound("click")
                self.game.change_state(STATE_MAIN_MENU)
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.game.change_state(STATE_MAIN_MENU)

    def update(self, dt: float):
        self.bg.update(dt)
        self.back_btn.update(dt, pygame.mouse.get_pos())

    def draw(self, surface: pygame.Surface):
        self.bg.draw(surface)
        font_title = pygame.font.SysFont("consolas", 48, bold=True)
        t = font_title.render("HIGH SCORES", True, COL_GOLD)
        surface.blit(t, (SCREEN_WIDTH // 2 - t.get_width() // 2, 60))

        font = pygame.font.SysFont("consolas", 28)
        scores = self.game.highscores.scores
        for i in range(10):
            y = 150 + i * 45
            if i < len(scores):
                col = COL_NEON_GREEN if i == 0 else COL_WHITE
                txt = font.render(f"{i+1:>2}.  {scores[i]:>8}", True, col)
            else:
                txt = font.render(f"{i+1:>2}.  --------", True, (60, 60, 80))
            surface.blit(txt, (SCREEN_WIDTH // 2 - txt.get_width() // 2, y))

        self.back_btn.draw(surface)

class AchievementsState(GameState):
    def __init__(self, game: "Game"):
        super().__init__(game)
        self.bg = BackgroundEffect()
        self.back_btn = Button("BACK", SCREEN_WIDTH // 2, 640)

    def handle_input(self, events: List[pygame.event.Event]):
        for event in events:
            if event.type == pygame.QUIT:
                self.game.running = False
            if self.back_btn.handle_event(event):
                self.game.audio.play_sound("click")
                self.game.change_state(STATE_MAIN_MENU)
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.game.change_state(STATE_MAIN_MENU)

    def update(self, dt: float):
        self.bg.update(dt)
        self.back_btn.update(dt, pygame.mouse.get_pos())

    def draw(self, surface: pygame.Surface):
        self.bg.draw(surface)
        font_title = pygame.font.SysFont("consolas", 48, bold=True)
        t = font_title.render("ACHIEVEMENTS", True, COL_CYAN)
        surface.blit(t, (SCREEN_WIDTH // 2 - t.get_width() // 2, 40))

        font_name = pygame.font.SysFont("consolas", 22, bold=True)
        font_desc = pygame.font.SysFont("consolas", 16)
        y = 120
        for adef in ACHIEVEMENT_DEFS:
            unlocked = self.game.achievements.unlocked.get(adef["id"], False)
            col = COL_NEON_GREEN if unlocked else (50, 50, 70)
            rect = pygame.Rect(200, y, 600, 55)
            draw_rounded_rect(surface, (15, 15, 35), rect, radius=8, alpha=200)
            if unlocked:
                draw_glow_rect(surface, COL_NEON_GREEN, rect, width=1, layers=2)
            else:
                pygame.draw.rect(surface, (40, 40, 60), rect, width=1, border_radius=8)

            icon = "★" if unlocked else "☆"
            name_txt = font_name.render(f"{icon} {adef['name']}", True, col)
            surface.blit(name_txt, (rect.x + 15, rect.y + 8))
            desc_txt = font_desc.render(adef["desc"], True,
                                        (180, 255, 200) if unlocked else (80, 80, 100))
            surface.blit(desc_txt, (rect.x + 15, rect.y + 32))
            y += 65

        self.back_btn.draw(surface)

class SettingsState(GameState):
    def __init__(self, game: "Game"):
        super().__init__(game)
        self.bg = BackgroundEffect()
        self.back_btn = Button("BACK", SCREEN_WIDTH // 2, 640)
        cx = SCREEN_WIDTH // 2
        self.music_slider = Slider(cx - 150, 180, 300,
                                   self.game.settings.get("music_volume"),
                                   "Music Volume")
        self.sfx_slider = Slider(cx - 150, 270, 300,
                                 self.game.settings.get("sfx_volume"),
                                 "SFX Volume")
        self.shake_on = self.game.settings.get("screen_shake")
        self.particle_idx = ["LOW", "MEDIUM", "HIGH"].index(
            self.game.settings.get("particle_density"))
        self.diff_idx = ["EASY", "NORMAL", "HARD", "INSANE"].index(
            self.game.settings.get("difficulty"))

        self.shake_btn = Button("SHAKE: ON" if self.shake_on else "SHAKE: OFF",
                                cx, 380, w=300, h=50, font_size=20)
        particles = ["LOW", "MEDIUM", "HIGH"]
        self.particle_btn = Button(f"PARTICLES: {particles[self.particle_idx]}",
                                   cx, 450, w=300, h=50, font_size=20)
        diffs = ["EASY", "NORMAL", "HARD", "INSANE"]
        self.diff_btn = Button(f"DIFFICULTY: {diffs[self.diff_idx]}",
                               cx, 520, w=300, h=50, font_size=20)

    def handle_input(self, events: List[pygame.event.Event]):
        for event in events:
            if event.type == pygame.QUIT:
                self.game.running = False
            self.music_slider.handle_event(event)
            self.sfx_slider.handle_event(event)
            if self.back_btn.handle_event(event):
                self.game.audio.play_sound("click")
                self._save()
                self.game.change_state(STATE_MAIN_MENU)
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self._save()
                self.game.change_state(STATE_MAIN_MENU)
            if self.shake_btn.handle_event(event):
                self.game.audio.play_sound("click")
                self.shake_on = not self.shake_on
                self.shake_btn.text = "SHAKE: ON" if self.shake_on else "SHAKE: OFF"
            if self.particle_btn.handle_event(event):
                self.game.audio.play_sound("click")
                self.particle_idx = (self.particle_idx + 1) % 3
                names = ["LOW", "MEDIUM", "HIGH"]
                self.particle_btn.text = f"PARTICLES: {names[self.particle_idx]}"
            if self.diff_btn.handle_event(event):
                self.game.audio.play_sound("click")
                self.diff_idx = (self.diff_idx + 1) % 4
                names = ["EASY", "NORMAL", "HARD", "INSANE"]
                self.diff_btn.text = f"DIFFICULTY: {names[self.diff_idx]}"

    def _save(self):
        self.game.settings.set("music_volume", self.music_slider.value)
        self.game.settings.set("sfx_volume", self.sfx_slider.value)
        self.game.settings.set("screen_shake", self.shake_on)
        self.game.settings.set("particle_density",
                               ["LOW", "MEDIUM", "HIGH"][self.particle_idx])
        self.game.settings.set("difficulty",
                               ["EASY", "NORMAL", "HARD", "INSANE"][self.diff_idx])
        self.game.settings.save()
        self.game.audio.update_volumes(
            self.music_slider.value / 100.0,
            self.sfx_slider.value / 100.0)

    def update(self, dt: float):
        self.bg.update(dt)
        mouse = pygame.mouse.get_pos()
        self.back_btn.update(dt, mouse)
        self.shake_btn.update(dt, mouse)
        self.particle_btn.update(dt, mouse)
        self.diff_btn.update(dt, mouse)
        self.game.audio.update_volumes(
            self.music_slider.value / 100.0,
            self.sfx_slider.value / 100.0)

    def draw(self, surface: pygame.Surface):
        self.bg.draw(surface)
        font_title = pygame.font.SysFont("consolas", 48, bold=True)
        t = font_title.render("SETTINGS", True, COL_CYAN)
        surface.blit(t, (SCREEN_WIDTH // 2 - t.get_width() // 2, 60))

        self.music_slider.draw(surface)
        self.sfx_slider.draw(surface)
        self.shake_btn.draw(surface)
        self.particle_btn.draw(surface)
        self.diff_btn.draw(surface)
        self.back_btn.draw(surface)

class UpgradeState(GameState):
    UPGRADES = [
        {"name": "SPEED+",   "desc": "Increase base speed by 1",    "key": "speed_up"},
        {"name": "LENGTH+",  "desc": "Grow 3 extra segments",       "key": "grow"},
        {"name": "SCORE+",   "desc": "+100 bonus score",            "key": "score"},
        {"name": "SHIELD",   "desc": "Gain a one-hit shield",       "key": "shield"},
    ]

    def __init__(self, game: "Game"):
        super().__init__(game)
        self.choices = random.sample(self.UPGRADES, 3)
        cx = SCREEN_WIDTH // 2
        self.buttons = [
            Button(f"{c['name']}: {c['desc']}", cx, 300 + i * 90,
                   w=500, h=70, font_size=20)
            for i, c in enumerate(self.choices)
        ]
        self.anim_t: float = 0.0

    def handle_input(self, events: List[pygame.event.Event]):
        for event in events:
            if event.type == pygame.QUIT:
                self.game.running = False
            for i, btn in enumerate(self.buttons):
                if btn.handle_event(event):
                    self.game.audio.play_sound("click")
                    self._apply(self.choices[i]["key"])
                    self.game.change_state(STATE_GAMEPLAY)

    def _apply(self, key: str):
        gs = self.game.gameplay_state
        if gs is None:
            return
        if key == "speed_up":
            gs.snake.base_speed = min(20, gs.snake.base_speed + 1)
        elif key == "grow":
            gs.snake.grow(3)
        elif key == "score":
            gs.score += 100
        elif key == "shield":
            gs.snake.shield_active = True

    def update(self, dt: float):
        self.anim_t = min(1.0, self.anim_t + dt * 3)
        mouse = pygame.mouse.get_pos()
        for btn in self.buttons:
            btn.update(dt, mouse)

    def draw(self, surface: pygame.Surface):
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        surface.blit(overlay, (0, 0))

        alpha = int(255 * ease_out_cubic(self.anim_t))
        font = pygame.font.SysFont("consolas", 48, bold=True)
        t = font.render("EVOLUTION!", True, COL_NEON_GREEN)
        t.set_alpha(alpha)
        surface.blit(t, (SCREEN_WIDTH // 2 - t.get_width() // 2, 160))

        sub = pygame.font.SysFont("consolas", 20).render(
            "Choose an upgrade:", True, COL_WHITE)
        sub.set_alpha(alpha)
        surface.blit(sub, (SCREEN_WIDTH // 2 - sub.get_width() // 2, 230))

        for btn in self.buttons:
            btn.draw(surface)

class PauseState(GameState):
    def __init__(self, game: "Game"):
        super().__init__(game)
        cx = SCREEN_WIDTH // 2
        self.buttons = [
            Button("RESUME", cx, 280),
            Button("RESTART", cx, 360),
            Button("MAIN MENU", cx, 440),
            Button("QUIT", cx, 520),
        ]

    def handle_input(self, events: List[pygame.event.Event]):
        for event in events:
            if event.type == pygame.QUIT:
                self.game.running = False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.game.change_state(STATE_GAMEPLAY)
            for i, btn in enumerate(self.buttons):
                if btn.handle_event(event):
                    self.game.audio.play_sound("click")
                    if i == 0:
                        self.game.change_state(STATE_GAMEPLAY)
                    elif i == 1:
                        self.game.change_state(STATE_GAMEPLAY, fresh=True)
                    elif i == 2:
                        self.game.change_state(STATE_MAIN_MENU)
                    elif i == 3:
                        self.game.running = False

    def update(self, dt: float):
        mouse = pygame.mouse.get_pos()
        for btn in self.buttons:
            btn.update(dt, mouse)

    def draw(self, surface: pygame.Surface):
        if self.game.gameplay_state:
            self.game.gameplay_state.draw(surface)
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 160))
        surface.blit(overlay, (0, 0))

        font = pygame.font.SysFont("consolas", 56, bold=True)
        t = font.render("PAUSED", True, COL_CYAN)
        surface.blit(t, (SCREEN_WIDTH // 2 - t.get_width() // 2, 150))

        for btn in self.buttons:
            btn.draw(surface)

class GameOverState(GameState):
    def __init__(self, game: "Game"):
        super().__init__(game)
        cx = SCREEN_WIDTH // 2
        self.buttons = [
            Button("RESTART", cx, 450),
            Button("MAIN MENU", cx, 530),
        ]
        self.anim_t: float = 0.0
        gs = self.game.gameplay_state
        self.score = gs.score if gs else 0
        self.high = self.game.highscores.best
        self.game.highscores.add(self.score)
        self.new_high = self.score > self.high and self.score > 0

    def handle_input(self, events: List[pygame.event.Event]):
        for event in events:
            if event.type == pygame.QUIT:
                self.game.running = False
            for i, btn in enumerate(self.buttons):
                if btn.handle_event(event):
                    self.game.audio.play_sound("click")
                    if i == 0:
                        self.game.change_state(STATE_GAMEPLAY, fresh=True)
                    elif i == 1:
                        self.game.change_state(STATE_MAIN_MENU)

    def update(self, dt: float):
        self.anim_t = min(1.0, self.anim_t + dt * 2)
        mouse = pygame.mouse.get_pos()
        for btn in self.buttons:
            btn.update(dt, mouse)

    def draw(self, surface: pygame.Surface):
        surface.fill(COL_BG)
        alpha = int(255 * ease_out_cubic(self.anim_t))

        font_big = pygame.font.SysFont("consolas", 64, bold=True)
        t = font_big.render("GAME OVER", True, (255, 60, 60))
        t.set_alpha(alpha)
        surface.blit(t, (SCREEN_WIDTH // 2 - t.get_width() // 2, 120))

        font = pygame.font.SysFont("consolas", 32)
        sc = font.render(f"Score: {self.score}", True, COL_WHITE)
        sc.set_alpha(alpha)
        surface.blit(sc, (SCREEN_WIDTH // 2 - sc.get_width() // 2, 240))

        hs = font.render(f"High Score: {self.game.highscores.best}", True, COL_GOLD)
        hs.set_alpha(alpha)
        surface.blit(hs, (SCREEN_WIDTH // 2 - hs.get_width() // 2, 290))

        if self.new_high:
            nh = pygame.font.SysFont("consolas", 24, bold=True).render(
                "NEW HIGH SCORE!", True, COL_NEON_GREEN)
            nh.set_alpha(alpha)
            surface.blit(nh, (SCREEN_WIDTH // 2 - nh.get_width() // 2, 340))

        for btn in self.buttons:
            btn.draw(surface)

class GameplayState(GameState):
    def __init__(self, game: "Game"):
        super().__init__(game)
        self.snake = Snake()
        self.food = Food()
        self.powerups: List[PowerUpFood] = []
        self.obstacles: List[Obstacle] = []
        self.particles = ParticleSystem(game.settings.particle_multiplier)
        self.shake = ScreenShake()
        self.score: int = 0
        self.foods_eaten: int = 0
        self.evolution_count: int = 0
        self.survive_time: float = 0.0
        self.score_popups: List[ScorePopup] = []
        self.powerup_timer: float = 0.0
        self.obstacle_timer: float = 0.0
        self.game_over_triggered: bool = False
        self.death_anim: float = 0.0 

        speed_mult, self.powerup_interval, self.obstacle_density = \
            game.settings.difficulty_tuple
        self.snake.base_speed *= speed_mult

        self.food.respawn(set(self.snake.segments))

    def _occupied_set(self) -> set:
        occ = set(self.snake.segments)
        occ.add(self.food.pos)
        for pu in self.powerups:
            occ.add(pu.pos)
        for ob in self.obstacles:
            occ.add(ob.pos)
        return occ

    def handle_input(self, events: List[pygame.event.Event]):
        for event in events:
            if event.type == pygame.QUIT:
                self.game.running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.game.change_state(STATE_PAUSE)
                elif event.key in (pygame.K_UP, pygame.K_w):
                    self.snake.set_direction(DIR_UP)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    self.snake.set_direction(DIR_DOWN)
                elif event.key in (pygame.K_LEFT, pygame.K_a):
                    self.snake.set_direction(DIR_LEFT)
                elif event.key in (pygame.K_RIGHT, pygame.K_d):
                    self.snake.set_direction(DIR_RIGHT)

    def update(self, dt: float):
        if self.game_over_triggered:
            self.death_anim += dt
            self.particles.update(dt)
            if self.death_anim > 1.5:
                self.game.change_state(STATE_GAME_OVER)
            return

        self.survive_time += dt
        self.particles.update(dt)
        self.shake.update(dt)
        self.food.update(dt)

        for pu in self.powerups:
            pu.update(dt)
        self.powerups = [pu for pu in self.powerups if pu.alive]

        self.powerup_timer += dt
        if self.powerup_timer >= self.powerup_interval:
            self.powerup_timer = 0
            self._spawn_powerup()

        self.obstacle_timer += dt
        if self.obstacle_timer >= 60:
            self.obstacle_timer = 0
            self._generate_obstacles()
        for ob in self.obstacles:
            ob.update(dt)

        for sp in self.score_popups:
            sp.update(dt)
        self.score_popups = [sp for sp in self.score_popups if sp.alive]

        stepped = self.snake.update(dt)
        if stepped:
            self._check_collisions()

        self.game.achievements.check(
            self.score, self.snake.length, self.snake.speed, self.survive_time)
        self.game.achievements.update(dt)

        time_bonus = self.survive_time / 120.0 

    def _check_collisions(self):
        if self.snake.check_wall_collision():
            self._die()
            return

        if self.snake.check_self_collision():
            if self.snake.shield_active:
                self.snake.shield_active = False
                if self.game.settings.get("screen_shake"):
                    self.shake.trigger(4)
            else:
                self._die()
                return

        for ob in self.obstacles:
            if self.snake.head == ob.pos:
                if self.snake.ghost_timer > 0:
                    pass 
                elif self.snake.shield_active:
                    self.snake.shield_active = False
                    self.obstacles.remove(ob)
                    if self.game.settings.get("screen_shake"):
                        self.shake.trigger(4)
                else:
                    self._die()
                    return

        if self.snake.head == self.food.pos:
            self.game.audio.play_sound("eat")
            self.snake.grow(1)
            self.snake.head_scale = 1.4
            score_val = 10 * (2 if self.snake.double_score_timer > 0 else 1)
            self.score += score_val
            self.foods_eaten += 1

            cx = self.food.pos[0] * CELL_SIZE + CELL_SIZE // 2
            cy = self.food.pos[1] * CELL_SIZE + CELL_SIZE // 2
            self.particles.emit(cx, cy, COL_FOOD, count=12, speed=120, life=0.6)
            self.score_popups.append(ScorePopup(cx, cy - 10, score_val, COL_FOOD))

            if self.game.settings.get("screen_shake"):
                self.shake.trigger(3)

            self.food.respawn(self._occupied_set())

            if self.foods_eaten % 5 == 0:
                self.evolution_count += 1
                self.game.achievements.evolution_count = self.evolution_count
                self.score += 50
                self.game.audio.play_sound("evolve")
                hx = self.snake.head[0] * CELL_SIZE + CELL_SIZE // 2
                hy = self.snake.head[1] * CELL_SIZE + CELL_SIZE // 2
                self.particles.emit(hx, hy, COL_NEON_GREEN,
                                    count=30, speed=200, life=1.0, size=4)
                self.game.change_state(STATE_UPGRADE)

        for pu in self.powerups[:]:
            if self.snake.head == pu.pos:
                self.game.audio.play_sound("powerup")
                self.snake.apply_powerup(pu.ptype)
                score_val = 25 * (2 if self.snake.double_score_timer > 0 else 1)
                self.score += score_val
                cx = pu.pos[0] * CELL_SIZE + CELL_SIZE // 2
                cy = pu.pos[1] * CELL_SIZE + CELL_SIZE // 2
                self.particles.emit(cx, cy, pu.colour,
                                    count=20, speed=150, life=0.8, size=4)
                self.score_popups.append(ScorePopup(cx, cy - 10, score_val, pu.colour))
                if pu.ptype == "ghost":
                    self.game.achievements.ghost_uses += 1
                self.powerups.remove(pu)

        if self.snake.split_timer > 0 and self.snake.split_segments:
            mirror_head = self.snake.split_segments[0] if self.snake.split_segments else None
            if mirror_head and mirror_head == self.food.pos:
                self.game.audio.play_sound("eat")
                self.snake.grow(1)
                score_val = 10 * (2 if self.snake.double_score_timer > 0 else 1)
                self.score += score_val
                self.foods_eaten += 1
                self.food.respawn(self._occupied_set())

    def _spawn_powerup(self):
        occ = self._occupied_set()
        ptype = random.choice(list(POWERUP_COLOURS.keys()))
        for _ in range(50):
            x = random.randint(0, GRID_COLS - 1)
            y = random.randint(0, GRID_ROWS - 1)
            if (x, y) not in occ:
                self.powerups.append(PowerUpFood(ptype, (x, y)))
                return

    def _generate_obstacles(self):
        self.obstacles.clear()
        occ = self._occupied_set()
        for seg in self.snake.segments:
            occ.add(seg)
        count = int(GRID_COLS * GRID_ROWS * self.obstacle_density)
        for _ in range(count):
            for _ in range(20):
                x = random.randint(0, GRID_COLS - 1)
                y = random.randint(0, GRID_ROWS - 1)
                if (x, y) not in occ:
                    hx, hy = self.snake.head
                    dx, dy = self.snake.direction
                    if (x, y) == (hx + dx, hy + dy):
                        continue
                    if (x, y) == (hx + dx * 2, hy + dy * 2):
                        continue
                    self.obstacles.append(Obstacle(x, y))
                    occ.add((x, y))
                    break

    def _die(self):
        if self.game_over_triggered:
            return
        self.game_over_triggered = True
        self.snake.alive = False
        self.game.audio.play_sound("gameover")
        if self.game.settings.get("screen_shake"):
            self.shake.trigger(12)
        for sx, sy in self.snake.segments:
            cx = sx * CELL_SIZE + CELL_SIZE // 2
            cy = sy * CELL_SIZE + CELL_SIZE // 2
            self.particles.emit(cx, cy, COL_SNAKE_HEAD,
                                count=5, speed=180, life=1.2, size=3, gravity=60)

    def draw(self, surface: pygame.Surface):
        ox, oy = self.shake.offset
        surface.fill(COL_BG)
        for x in range(0, SCREEN_WIDTH, CELL_SIZE):
            pygame.draw.line(surface, COL_GRID, (x + ox, 0), (x + ox, SCREEN_HEIGHT), 1)
        for y in range(0, SCREEN_HEIGHT, CELL_SIZE):
            pygame.draw.line(surface, COL_GRID, (0, y + oy), (SCREEN_WIDTH, y + oy), 1)

        saved_clip = surface.get_clip()
        surface.set_clip(surface.get_rect())

        for ob in self.obstacles:
            ob.draw(surface, ox, oy)

        self.food.draw(surface, ox, oy)

        for pu in self.powerups:
            pu.draw(surface, ox, oy)

        if not self.game_over_triggered:
            self.snake.draw(surface, self.particles, ox, oy)

        self.particles.draw(surface, ox, oy)

        surface.set_clip(saved_clip)

        for sp in self.score_popups:
            sp.draw(surface)

        self._draw_ui(surface)

        self.game.achievements.draw(surface)

        if self.game_over_triggered:
            alpha = min(200, int(self.death_anim * 150))
            overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, alpha))
            surface.blit(overlay, (0, 0))

    def _draw_ui(self, surface: pygame.Surface):
        font = pygame.font.SysFont("consolas", 24, bold=True)
        sc_txt = font.render(f"Score: {self.score}", True, COL_WHITE)
        surface.blit(sc_txt, (15, 10))
        len_txt = font.render(f"Length: {self.snake.length}", True, COL_WHITE)
        surface.blit(len_txt, (15, 38))
        hs_txt = pygame.font.SysFont("consolas", 18).render(
            f"Best: {self.game.highscores.best}", True, (120, 120, 160))
        surface.blit(hs_txt, (15, 66))

        indicators = []
        if self.snake.speed_boost_timer > 0:
            indicators.append(("SPD", POWERUP_COLOURS["speed"],
                                self.snake.speed_boost_timer))
        if self.snake.ghost_timer > 0:
            indicators.append(("GHO", POWERUP_COLOURS["ghost"],
                                self.snake.ghost_timer))
        if self.snake.double_score_timer > 0:
            indicators.append(("x2", POWERUP_COLOURS["double"],
                                self.snake.double_score_timer))
        if self.snake.split_timer > 0:
            indicators.append(("SPL", POWERUP_COLOURS["split"],
                                self.snake.split_timer))
        if self.snake.shield_active:
            indicators.append(("SHD", POWERUP_COLOURS["shield"], 99))

        small_font = pygame.font.SysFont("consolas", 16, bold=True)
        for i, (label, col, timer) in enumerate(indicators):
            x = SCREEN_WIDTH - 70 * (i + 1) - 10
            y = 10
            rect = pygame.Rect(x, y, 60, 28)
            draw_rounded_rect(surface, (10, 10, 30), rect, radius=6, alpha=200)
            draw_glow_rect(surface, col, rect, width=1, layers=2)
            t = small_font.render(label, True, col)
            surface.blit(t, (rect.centerx - t.get_width() // 2,
                             rect.centery - t.get_height() // 2))

        progress = self.foods_eaten % 5
        bar_w = 150
        bar_h = 10
        bar_x = SCREEN_WIDTH // 2 - bar_w // 2
        bar_y = 12
        pygame.draw.rect(surface, (30, 30, 60),
                         (bar_x, bar_y, bar_w, bar_h), border_radius=4)
        fill = int(bar_w * progress / 5)
        if fill > 0:
            pygame.draw.rect(surface, COL_NEON_GREEN,
                             (bar_x, bar_y, fill, bar_h), border_radius=4)
        evo_label = pygame.font.SysFont("consolas", 12).render(
            f"Evolution {self.evolution_count}", True, (100, 200, 150))
        surface.blit(evo_label,
                     (SCREEN_WIDTH // 2 - evo_label.get_width() // 2, bar_y + 14))

class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Snake Evolution")
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        self.clock = pygame.time.Clock()
        self.running: bool = True

        self.settings = SettingsManager()
        self.audio = AudioManager()
        self.audio.update_volumes(
            self.settings.get("music_volume") / 100.0,
            self.settings.get("sfx_volume") / 100.0)
        self.highscores = HighScoreManager()
        self.achievements = AchievementManager()

        self.gameplay_state: Optional[GameplayState] = None
        self.current_state: GameState = MainMenuState(self)
        self.current_state_name: str = STATE_MAIN_MENU

        self.audio.start_music()

    def change_state(self, state_name: str, fresh: bool = False):
        if state_name == STATE_MAIN_MENU:
            self.gameplay_state = None
            self.current_state = MainMenuState(self)
        elif state_name == STATE_GAMEPLAY:
            if self.gameplay_state is None or fresh:
                self.gameplay_state = GameplayState(self)
            self.current_state = self.gameplay_state
        elif state_name == STATE_PAUSE:
            self.current_state = PauseState(self)
        elif state_name == STATE_GAME_OVER:
            self.current_state = GameOverState(self)
        elif state_name == STATE_UPGRADE:
            self.current_state = UpgradeState(self)
        elif state_name == STATE_HOW_TO_PLAY:
            self.current_state = HowToPlayState(self)
        elif state_name == STATE_SETTINGS:
            self.current_state = SettingsState(self)
        elif state_name == STATE_ACHIEVEMENTS:
            self.current_state = AchievementsState(self)
        elif state_name == STATE_HIGHSCORES:
            self.current_state = HighScoresState(self)
        self.current_state_name = state_name

    def run(self):
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            dt = min(dt, 0.05)

            events = pygame.event.get()
            for event in events:
                if event.type == pygame.QUIT:
                    self.running = False

            self.current_state.handle_input(events)
            self.current_state.update(dt)
            self.current_state.draw(self.screen)

            pygame.display.flip()

        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    game = Game()
    game.run()