import pygame
import sys
import math
import random
import json
import os
import struct
from typing import List, Tuple, Optional, Dict, Any

SCREEN_WIDTH  = 1000
SCREEN_HEIGHT = 700
FPS           = 60
CELL_SIZE     = 20
GRID_COLS     = SCREEN_WIDTH  // CELL_SIZE
GRID_ROWS     = SCREEN_HEIGHT // CELL_SIZE

COL_BG         = (10, 10, 25)
COL_GRID       = (25, 50, 100)
COL_SNAKE_HEAD = (0, 255, 120)
COL_FOOD       = (255, 60, 60)
COL_WHITE      = (255, 255, 255)
COL_CYAN       = (0, 255, 255)
COL_NEON_GREEN = (0, 255, 120)
COL_DARK_PANEL = (20, 20, 50)
COL_BORDER     = (0, 180, 255)
COL_GOLD       = (255, 215, 0)

POWERUP_COLOURS = {
    "speed":   (255, 220, 0),
    "ghost":   (180, 0, 255),
    "shield":  (0, 140, 255),
    "double":  (255, 215, 0),
    "magnet":  (255, 80, 180),
    "shrink":  (0, 220, 255),
}

DIR_UP    = (0, -1)
DIR_DOWN  = (0,  1)
DIR_LEFT  = (-1, 0)
DIR_RIGHT = (1,  0)

DIFFICULTY = {
    "EASY":   (0.7, 12, 0.015),
    "NORMAL": (1.0, 10, 0.030),
    "HARD":   (1.3,  8, 0.050),
    "INSANE": (1.7,  6, 0.080),
}

SAVE_DIR          = os.path.join(os.path.expanduser("~"), ".snake_evolution")
SETTINGS_FILE     = os.path.join(SAVE_DIR, "settings.json")
HIGHSCORE_FILE    = os.path.join(SAVE_DIR, "highscore.txt")
ACHIEVEMENTS_FILE = os.path.join(SAVE_DIR, "achievements.json")
os.makedirs(SAVE_DIR, exist_ok=True)

STATE_MAIN_MENU    = "MAIN_MENU"
STATE_SETTINGS     = "SETTINGS_MENU"
STATE_ACHIEVEMENTS = "ACHIEVEMENTS_MENU"
STATE_HOW_TO_PLAY  = "HOW_TO_PLAY"
STATE_GAMEPLAY     = "GAMEPLAY"
STATE_PAUSE        = "PAUSE_MENU"
STATE_GAME_OVER    = "GAME_OVER"
STATE_UPGRADE      = "UPGRADE"
STATE_HIGHSCORES   = "HIGHSCORES"

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def lerp(a, b, t):
    return a + (b - a) * t

def ease_out_cubic(t):
    return 1.0 - (1.0 - t) ** 3

def ease_in_out_quad(t):
    return 2*t*t if t < 0.5 else 1 - (-2*t+2)**2/2

def draw_glow_circle(surface, colour, center, radius, layers=4):
    gs = pygame.Surface((radius*4, radius*4), pygame.SRCALPHA)
    for i in range(layers, 0, -1):
        alpha = max(10, 60 // i)
        r = radius + i*3
        pygame.draw.circle(gs, (*colour, alpha), (radius*2, radius*2), r)
    pygame.draw.circle(gs, (*colour, 220), (radius*2, radius*2), radius)
    surface.blit(gs, (center[0]-radius*2, center[1]-radius*2), special_flags=pygame.BLEND_ADD)

def draw_glow_rect(surface, colour, rect, width=2, layers=3):
    for i in range(layers, 0, -1):
        alpha = max(15, 80 // i)
        exp = rect.inflate(i*4, i*4)
        s = pygame.Surface((exp.width, exp.height), pygame.SRCALPHA)
        pygame.draw.rect(s, (*colour, alpha), s.get_rect(), width+i)
        surface.blit(s, exp.topleft, special_flags=pygame.BLEND_ADD)
    pygame.draw.rect(surface, colour, rect, width)

def draw_rounded_rect(surface, colour, rect, radius=8, alpha=255):
    s = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
    col = (*colour[:3], alpha) if len(colour) == 3 else colour
    pygame.draw.rect(s, col, s.get_rect(), border_radius=radius)
    surface.blit(s, rect.topleft)

def generate_tone(frequency=440.0, duration=0.1, volume=0.3, sample_rate=22050):
    n = int(sample_rate * duration)
    buf = bytearray()
    for i in range(n):
        t   = i / sample_rate
        env = max(0.0, 1.0 - t/duration) ** 2
        val = math.sin(2.0*math.pi*frequency*t) * volume * env
        buf.extend(struct.pack('<h', int(clamp(val, -1.0, 1.0)*32767)))
    return pygame.mixer.Sound(buffer=bytes(buf))

def generate_noise_burst(duration=0.05, volume=0.2, sample_rate=22050):
    n = int(sample_rate * duration)
    buf = bytearray()
    for i in range(n):
        env = max(0.0, 1.0 - i/n) ** 3
        val = (random.random()*2 - 1) * volume * env
        buf.extend(struct.pack('<h', int(clamp(val, -1.0, 1.0)*32767)))
    return pygame.mixer.Sound(buffer=bytes(buf))

class AudioManager:
    def __init__(self):
        self.enabled = True
        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
        except pygame.error:
            self.enabled = False
        self.sounds: Dict[str, pygame.mixer.Sound] = {}
        self.music_volume = 0.5
        self.sfx_volume   = 0.7
        self._sfx_sound   = None
        self._has_external_music = False
        self._music_sound = None
        if self.enabled:
            self._load_external_audio()
            self._generate_sounds()
            if not self._has_external_music:
                self._generate_music()
        self.music_channel = None

    def _load_external_audio(self):
        mp = os.path.join(_SCRIPT_DIR, "music.mp3")
        sp = os.path.join(_SCRIPT_DIR, "sfx.mp3")
        if os.path.isfile(mp):
            try:
                pygame.mixer.music.load(mp)
                self._has_external_music = True
            except pygame.error:
                pass
        if os.path.isfile(sp):
            try:
                self._sfx_sound = pygame.mixer.Sound(sp)
            except pygame.error:
                pass

    def _generate_sounds(self):
        self.sounds["hover"]   = generate_tone(800, 0.04, 0.15)
        self.sounds["click"]   = generate_tone(600, 0.08, 0.25)
        self.sounds["eat"]     = generate_tone(880, 0.10, 0.30)
        self.sounds["combo"]   = generate_tone(1100, 0.12, 0.35)
        self.sounds["powerup"] = self._make_powerup_sound()
        self.sounds["evolve"]  = self._make_evolve_sound()
        self.sounds["gameover"]= self._make_gameover_sound()

    def _make_powerup_sound(self):
        sr, dur = 22050, 0.3
        n = int(sr*dur)
        buf = bytearray()
        freqs = [440, 554, 659, 880]
        seg = n // len(freqs)
        for freq in freqs:
            for i in range(seg):
                env = max(0.0, 1.0 - i/seg) ** 1.5
                val = math.sin(2*math.pi*freq*(i/sr)) * 0.25 * env
                buf.extend(struct.pack('<h', int(clamp(val,-1,1)*32767)))
        return pygame.mixer.Sound(buffer=bytes(buf))

    def _make_evolve_sound(self):
        sr, dur = 22050, 0.6
        n = int(sr*dur)
        buf = bytearray()
        for i in range(n):
            t   = i/sr
            freq = 300 + 600*(t/dur)
            env  = max(0.0, 1.0 - t/dur)
            val  = math.sin(2*math.pi*freq*t) * 0.3 * env
            buf.extend(struct.pack('<h', int(clamp(val,-1,1)*32767)))
        return pygame.mixer.Sound(buffer=bytes(buf))

    def _make_gameover_sound(self):
        sr, dur = 22050, 0.8
        n = int(sr*dur)
        buf = bytearray()
        for i in range(n):
            t    = i/sr
            freq = 600 - 400*(t/dur)
            env  = max(0.0, 1.0 - t/dur) ** 2
            val  = math.sin(2*math.pi*freq*t) * 0.3 * env
            buf.extend(struct.pack('<h', int(clamp(val,-1,1)*32767)))
        return pygame.mixer.Sound(buffer=bytes(buf))

    def _generate_music(self):
        sr   = 22050
        beat = 60.0/120
        bars = 4
        n    = int(sr * beat * 4 * bars)
        buf  = bytearray()
        bass = [110, 110, 146.83, 130.81] * bars
        seg  = n // len(bass)
        for freq in bass:
            for i in range(seg):
                t   = i/sr
                env = max(0.0, 1.0 - i/seg) ** 1.2
                val = (math.sin(2*math.pi*freq*t)*0.15 +
                       math.sin(2*math.pi*freq*2*t)*0.05) * env
                buf.extend(struct.pack('<h', int(clamp(val,-1,1)*32767)))
        self._music_sound = pygame.mixer.Sound(buffer=bytes(buf))

    def play_sound(self, name: str):
        if not self.enabled:
            return
        if self._sfx_sound:
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
            pygame.mixer.music.set_volume(self.music_volume*0.6)
            pygame.mixer.music.play(loops=-1)
        elif self._music_sound:
            self._music_sound.set_volume(self.music_volume*0.4)
            self.music_channel = self._music_sound.play(loops=-1)

    def stop_music(self):
        if not self.enabled:
            return
        if self._has_external_music:
            pygame.mixer.music.stop()
        elif self.music_channel:
            self.music_channel.stop()

    def update_volumes(self, mv, sv):
        self.music_volume = mv
        self.sfx_volume   = sv
        if not self.enabled:
            return
        if self._has_external_music:
            pygame.mixer.music.set_volume(mv*0.6)
        elif self.music_channel and self._music_sound:
            self._music_sound.set_volume(mv*0.4)

class SettingsManager:
    DEFAULTS: Dict[str, Any] = {
        "music_volume":    50,
        "sfx_volume":      70,
        "screen_shake":    True,
        "particle_density":"MEDIUM",
        "difficulty":      "NORMAL",
    }

    def __init__(self):
        self.data = dict(self.DEFAULTS)
        self.load()

    def load(self):
        try:
            with open(SETTINGS_FILE) as f:
                self.data.update(json.load(f))
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def save(self):
        with open(SETTINGS_FILE, "w") as f:
            json.dump(self.data, f, indent=2)

    def get(self, key):
        return self.data.get(key, self.DEFAULTS.get(key))

    def set(self, key, value):
        self.data[key] = value

    @property
    def particle_multiplier(self):
        return {"LOW": 0.4, "MEDIUM": 1.0, "HIGH": 2.0}.get(self.data["particle_density"], 1.0)

    @property
    def difficulty_tuple(self):
        return DIFFICULTY.get(self.data["difficulty"], DIFFICULTY["NORMAL"])

class HighScoreManager:
    def __init__(self):
        self.scores: List[int] = []
        self.load()

    def load(self):
        try:
            with open(HIGHSCORE_FILE) as f:
                self.scores = [int(l.strip()) for l in f if l.strip().isdigit()]
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

    def clear(self):
        self.scores = []
        self.save()

    @property
    def best(self):
        return self.scores[0] if self.scores else 0

ACHIEVEMENT_DEFS: List[Dict[str, str]] = [
    {"id": "first_meal",       "name": "FIRST MEAL",        "desc": "Eat your first food."},
    {"id": "growing_fast",     "name": "GROWING FAST",      "desc": "Reach snake length 15."},
    {"id": "unstoppable",      "name": "UNSTOPPABLE",       "desc": "Reach score 1000."},
    {"id": "ghost_master",     "name": "GHOST MASTER",      "desc": "Use Ghost Mode 5 times."},
    {"id": "survivor",         "name": "SURVIVOR",          "desc": "Survive for 5 minutes."},
    {"id": "speed_demon",      "name": "SPEED DEMON",       "desc": "Reach max snake speed."},
    {"id": "evolution_master", "name": "EVOLUTION MASTER",  "desc": "Trigger 10 evolution events."},
    {"id": "combo_king",       "name": "COMBO KING",        "desc": "Reach a x5 combo."},
    {"id": "magnet_lover",     "name": "MAGNET LOVER",      "desc": "Collect 3 Magnet power-ups."},
]

class AchievementNotification:
    def __init__(self, name: str):
        self.name     = name
        self.timer    = 0.0
        self.duration = 3.0
        self.y_offset = -60.0

    @property
    def alive(self):
        return self.timer < self.duration

    def update(self, dt):
        self.timer += dt
        if self.timer < 0.4:
            self.y_offset = lerp(-60, 10, ease_out_cubic(self.timer/0.4))
        elif self.timer > self.duration - 0.4:
            self.y_offset = lerp(10, -60, (self.timer-(self.duration-0.4))/0.4)

    def draw(self, surface, index):
        y    = int(self.y_offset) + index*55
        rect = pygame.Rect(SCREEN_WIDTH-310, y, 300, 45)
        draw_rounded_rect(surface, (10,10,40), rect, radius=8, alpha=220)
        draw_glow_rect(surface, COL_NEON_GREEN, rect, width=1, layers=2)
        font = pygame.font.SysFont("consolas", 16, bold=True)
        txt  = font.render(f"UNLOCKED: {self.name}", True, COL_NEON_GREEN)
        surface.blit(txt, (rect.x+10, rect.y+13))

class AchievementManager:
    def __init__(self):
        self.unlocked      = {a["id"]: False for a in ACHIEVEMENT_DEFS}
        self.notifications: List[AchievementNotification] = []
        self.ghost_uses    = 0
        self.magnet_uses   = 0
        self.evolution_count = 0
        self.load()

    def load(self):
        try:
            with open(ACHIEVEMENTS_FILE) as f:
                for k, v in json.load(f).items():
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

    def check(self, score, length, speed, survive_time, foods_eaten, max_combo):
        if foods_eaten >= 1:          self.unlock("first_meal")
        if length >= 15:              self.unlock("growing_fast")
        if score >= 1000:             self.unlock("unstoppable")
        if self.ghost_uses >= 5:      self.unlock("ghost_master")
        if survive_time >= 300:       self.unlock("survivor")
        if speed >= 20:               self.unlock("speed_demon")
        if self.evolution_count >= 10:self.unlock("evolution_master")
        if max_combo >= 5:            self.unlock("combo_king")
        if self.magnet_uses >= 3:     self.unlock("magnet_lover")

    def update(self, dt):
        for n in self.notifications:
            n.update(dt)
        self.notifications = [n for n in self.notifications if n.alive]

    def draw(self, surface):
        for i, n in enumerate(self.notifications):
            n.draw(surface, i)

class Particle:
    __slots__ = ("x","y","vx","vy","colour","size","life","max_life","gravity")

    def __init__(self, x, y, vx, vy, colour, size=3.0, life=1.0, gravity=0.0):
        self.x=x; self.y=y; self.vx=vx; self.vy=vy
        self.colour=colour; self.size=size
        self.life=life; self.max_life=life; self.gravity=gravity

    @property
    def alive(self):
        return self.life > 0

    def update(self, dt):
        self.x  += self.vx*dt
        self.y  += self.vy*dt
        self.vy += self.gravity*dt
        self.life -= dt

    def draw(self, surface, ox=0, oy=0):
        if self.life <= 0:
            return
        ratio = max(0.0, self.life/self.max_life)
        alpha = int(255*ratio)
        r     = max(1, int(self.size*ratio))
        s     = pygame.Surface((r*4, r*4), pygame.SRCALPHA)
        pygame.draw.circle(s, (*self.colour, alpha),    (r*2, r*2), r)
        pygame.draw.circle(s, (*self.colour, alpha//3), (r*2, r*2), r*2)
        surface.blit(s, (int(self.x)-r*2+ox, int(self.y)-r*2+oy),
                     special_flags=pygame.BLEND_ADD)

class ParticleSystem:
    def __init__(self, multiplier=1.0):
        self.particles: List[Particle] = []
        self.multiplier = multiplier

    def emit(self, x, y, colour, count=10, speed=100, life=0.8, size=3.0, gravity=0.0):
        actual = max(1, int(count*self.multiplier))
        for _ in range(actual):
            angle = random.uniform(0, math.pi*2)
            spd   = random.uniform(speed*0.3, speed)
            vx    = math.cos(angle)*spd
            vy    = math.sin(angle)*spd
            lt    = random.uniform(life*0.5, life)
            sz    = random.uniform(size*0.5, size)
            self.particles.append(Particle(x, y, vx, vy, colour, sz, lt, gravity))

    def emit_trail(self, x, y, colour):
        if random.random() > self.multiplier*0.5:
            return
        vx = random.uniform(-20, 20)
        vy = random.uniform(-20, 20)
        self.particles.append(Particle(x, y, vx, vy, colour, 2.0, 0.4))

    def update(self, dt):
        for p in self.particles:
            p.update(dt)
        self.particles = [p for p in self.particles if p.alive]

    def draw(self, surface, ox=0, oy=0):
        for p in self.particles:
            p.draw(surface, ox, oy)

class BackgroundEffect:
    def __init__(self):
        self.grid_offset  = 0.0
        self.bg_particles = []
        for _ in range(40):
            self.bg_particles.append({
                "x": random.uniform(0, SCREEN_WIDTH),
                "y": random.uniform(0, SCREEN_HEIGHT),
                "vx": random.uniform(-15, 15),
                "vy": random.uniform(-15, 15),
                "size":  random.uniform(1, 3),
                "alpha": random.uniform(30, 100),
            })

    def update(self, dt):
        self.grid_offset = (self.grid_offset + 15*dt) % CELL_SIZE
        for p in self.bg_particles:
            p["x"] = (p["x"] + p["vx"]*dt) % SCREEN_WIDTH
            p["y"] = (p["y"] + p["vy"]*dt) % SCREEN_HEIGHT

    def draw(self, surface):
        surface.fill(COL_BG)
        off = int(self.grid_offset)
        for x in range(0, SCREEN_WIDTH+CELL_SIZE, CELL_SIZE):
            pygame.draw.line(surface, COL_GRID, (x, 0), (x, SCREEN_HEIGHT), 1)
        for y in range(0, SCREEN_HEIGHT+CELL_SIZE, CELL_SIZE):
            pygame.draw.line(surface, COL_GRID, (0, y+off), (SCREEN_WIDTH, y+off), 1)
        for p in self.bg_particles:
            sz = int(p["size"])
            s  = pygame.Surface((sz*4, sz*4), pygame.SRCALPHA)
            pygame.draw.circle(s, (100,180,255,int(p["alpha"])), (sz*2, sz*2), sz)
            surface.blit(s, (int(p["x"])-sz*2, int(p["y"])-sz*2), special_flags=pygame.BLEND_ADD)

class Button:
    def __init__(self, text, x, y, w=300, h=60, font_size=26):
        self.text      = text
        self.base_rect = pygame.Rect(x-w//2, y-h//2, w, h)
        self.rect      = self.base_rect.copy()
        self.font      = pygame.font.SysFont("consolas", font_size, bold=True)
        self.hovered   = False
        self.clicked   = False
        self.click_timer   = 0.0
        self.hover_scale   = 1.0

    def handle_event(self, event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.clicked    = True
                self.click_timer = 0.15
                return True
        return False

    def update(self, dt, mouse_pos):
        self.hovered    = self.rect.collidepoint(mouse_pos)
        target          = 1.08 if self.hovered else 1.0
        self.hover_scale = lerp(self.hover_scale, target, dt*10)
        if self.click_timer > 0:
            self.click_timer -= dt
            if self.click_timer <= 0:
                self.clicked = False
        w = int(self.base_rect.width  * self.hover_scale)
        h = int(self.base_rect.height * self.hover_scale)
        self.rect = pygame.Rect(self.base_rect.centerx-w//2, self.base_rect.centery-h//2, w, h)

    def draw(self, surface):
        draw_rounded_rect(surface, COL_DARK_PANEL, self.rect, radius=10, alpha=200)
        border_col = COL_NEON_GREEN if self.hovered else COL_BORDER
        if self.clicked:
            border_col = COL_WHITE
        draw_glow_rect(surface, border_col, self.rect, width=2, layers=4 if self.hovered else 2)
        txt = self.font.render(self.text, True, COL_WHITE)
        surface.blit(txt, (self.rect.centerx-txt.get_width()//2,
                           self.rect.centery-txt.get_height()//2))

class Slider:
    def __init__(self, x, y, w, value=50, label=""):
        self.rect     = pygame.Rect(x, y, w, 30)
        self.value    = value
        self.label    = label
        self.dragging = False
        self.font     = pygame.font.SysFont("consolas", 18)

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.inflate(10,20).collidepoint(event.pos):
                self.dragging = True
                self._update_value(event.pos[0])
        elif event.type == pygame.MOUSEBUTTONUP:
            self.dragging = False
        elif event.type == pygame.MOUSEMOTION and self.dragging:
            self._update_value(event.pos[0])

    def _update_value(self, mx):
        self.value = int(clamp((mx-self.rect.x)/self.rect.width*100, 0, 100))

    def draw(self, surface):
        lbl = self.font.render(f"{self.label}: {self.value}", True, COL_WHITE)
        surface.blit(lbl, (self.rect.x, self.rect.y-22))
        pygame.draw.rect(surface, (40,40,80), self.rect, border_radius=5)
        fw = int(self.rect.width*self.value/100)
        pygame.draw.rect(surface, COL_NEON_GREEN,
                         pygame.Rect(self.rect.x, self.rect.y, fw, self.rect.height),
                         border_radius=5)
        pygame.draw.circle(surface, COL_WHITE, (self.rect.x+fw, self.rect.centery), 10)

class ScorePopup:
    def __init__(self, x, y, value, colour=COL_WHITE):
        self.x        = x
        self.y        = float(y)
        self.value    = value
        self.colour   = colour
        self.timer    = 0.0
        self.duration = 1.0
        self.font     = pygame.font.SysFont("consolas", 20, bold=True)

    @property
    def alive(self):
        return self.timer < self.duration

    def update(self, dt):
        self.timer += dt
        self.y     -= 40*dt

    def draw(self, surface):
        if not self.alive:
            return
        alpha = int(255*(1.0 - self.timer/self.duration))
        txt   = self.font.render(f"+{self.value}", True, self.colour)
        txt.set_alpha(alpha)
        surface.blit(txt, (self.x, int(self.y)))

class ComboDisplay:
    def __init__(self):
        self.combo      = 0
        self.max_combo  = 0
        self.timer      = 0.0
        self.window     = 2.5
        self.anim       = 0.0
        self.font_big   = pygame.font.SysFont("consolas", 32, bold=True)
        self.font_small = pygame.font.SysFont("consolas", 16)

    def feed(self):
        self.combo  += 1
        self.timer   = self.window
        self.anim    = 1.0
        self.max_combo = max(self.max_combo, self.combo)

    def multiplier(self):
        if self.combo >= 8: return 4
        if self.combo >= 5: return 3
        if self.combo >= 3: return 2
        return 1

    def reset(self):
        self.combo = 0
        self.timer = 0.0

    def update(self, dt):
        if self.timer > 0:
            self.timer -= dt
            if self.timer <= 0:
                self.combo = 0
        self.anim = max(0.0, self.anim - dt*4)

    def draw(self, surface):
        if self.combo < 2:
            return
        scale  = 1.0 + self.anim*0.3
        mult   = self.multiplier()
        col    = [COL_WHITE, COL_WHITE, COL_GOLD, (255,120,0), (255,50,50)][min(mult, 4)]
        label  = self.font_big.render(f"x{self.combo} COMBO", True, col)
        w      = int(label.get_width()*scale)
        h      = int(label.get_height()*scale)
        label  = pygame.transform.scale(label, (w, h))
        x      = SCREEN_WIDTH//2 - w//2
        y      = SCREEN_HEIGHT - 60
        label.set_alpha(220)
        surface.blit(label, (x, y))
        sub    = self.font_small.render(f"  {mult}x score  ", True, col)
        surface.blit(sub, (SCREEN_WIDTH//2 - sub.get_width()//2, y+h+2))

class Snake:
    def __init__(self, start_x=10, start_y=17):
        self.segments: List[Tuple[int,int]] = [(start_x-i, start_y) for i in range(4)]
        self.direction      = DIR_RIGHT
        self.next_direction = DIR_RIGHT
        self.grow_pending   = 0
        self.base_speed     = 8.0
        self.speed          = 8.0
        self.move_timer     = 0.0
        self.alive          = True

        self.speed_boost_timer  = 0.0
        self.ghost_timer        = 0.0
        self.shield_active      = False
        self.double_score_timer = 0.0
        self.magnet_timer       = 0.0
        self.shrink_pending     = False

        self.head_scale = 1.0
        self.bounce_available = False

    @property
    def head(self):
        return self.segments[0]

    @property
    def length(self):
        return len(self.segments)

    def set_direction(self, d):
        if d[0]+self.direction[0] == 0 and d[1]+self.direction[1] == 0:
            return
        self.next_direction = d

    def update(self, dt) -> bool:
        if not self.alive:
            return False

        if self.speed_boost_timer > 0:
            self.speed_boost_timer -= dt
            self.speed = self.base_speed * 1.6
        else:
            self.speed = self.base_speed

        if self.ghost_timer        > 0: self.ghost_timer        -= dt
        if self.double_score_timer > 0: self.double_score_timer -= dt
        if self.magnet_timer       > 0: self.magnet_timer       -= dt

        self.head_scale = lerp(self.head_scale, 1.0, dt*8)

        self.move_timer += dt
        if self.move_timer >= 1.0/self.speed:
            self.move_timer -= 1.0/self.speed
            self.direction   = self.next_direction
            self._step()
            return True
        return False

    def _step(self):
        hx, hy = self.head
        nx = hx + self.direction[0]
        ny = hy + self.direction[1]
        if self.ghost_timer > 0:
            nx %= GRID_COLS
            ny %= GRID_ROWS
        self.segments.insert(0, (nx, ny))
        if self.shrink_pending and len(self.segments) > 4:
            remove = min(3, len(self.segments)-4)
            self.segments = self.segments[:-remove]
            self.shrink_pending = False
        elif self.grow_pending > 0:
            self.grow_pending -= 1
        else:
            self.segments.pop()

    def grow(self, amount=1):
        self.grow_pending += amount

    def check_wall_collision(self):
        if self.ghost_timer > 0:
            return False
        hx, hy = self.head
        return hx < 0 or hx >= GRID_COLS or hy < 0 or hy >= GRID_ROWS

    def wall_bounce(self):
        hx, hy = self.head
        dx, dy = self.direction
        if hx <= 0 or hx >= GRID_COLS-1:
            dx = -dx
        if hy <= 0 or hy >= GRID_ROWS-1:
            dy = -dy
        self.direction      = (dx, dy)
        self.next_direction = (dx, dy)
        self.bounce_available = False

    def check_self_collision(self):
        return self.head in self.segments[1:]

    def apply_powerup(self, ptype: str):
        if   ptype == "speed":  self.speed_boost_timer  = 6.0
        elif ptype == "ghost":  self.ghost_timer         = 5.0
        elif ptype == "shield": self.shield_active       = True
        elif ptype == "double": self.double_score_timer  = 8.0
        elif ptype == "magnet": self.magnet_timer        = 6.0
        elif ptype == "shrink": self.shrink_pending      = True

    def draw(self, surface, particles, ox=0, oy=0):
        total = len(self.segments)
        ghost = self.ghost_timer > 0
        magnet= self.magnet_timer > 0

        for i, (sx, sy) in enumerate(reversed(self.segments)):
            ratio  = 1.0 - i/max(1, total)
            g      = int(lerp(80, 255, ratio))
            base_col = (0, g, int(lerp(40, 120, ratio)))
            if magnet:
                base_col = (int(lerp(255,0,ratio)), int(lerp(80,255,ratio)), int(lerp(180,80,ratio)))
            alpha  = 110 if ghost else 255
            shrink = int(lerp(2, 0, ratio))
            rect   = pygame.Rect(sx*CELL_SIZE+shrink+ox, sy*CELL_SIZE+shrink+oy,
                                 CELL_SIZE-shrink*2, CELL_SIZE-shrink*2)
            s = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            pygame.draw.rect(s, (*base_col, alpha), s.get_rect(), border_radius=5)
            surface.blit(s, rect.topleft)
            if self.speed_boost_timer > 0 and i == total-1:
                particles.emit_trail(sx*CELL_SIZE+CELL_SIZE//2,
                                     sy*CELL_SIZE+CELL_SIZE//2, COL_SNAKE_HEAD)

        hx, hy = self.head
        hc = (hx*CELL_SIZE+CELL_SIZE//2+ox, hy*CELL_SIZE+CELL_SIZE//2+oy)
        hr = int(CELL_SIZE//2 * self.head_scale)
        head_col = (0, 200, 255) if magnet else COL_SNAKE_HEAD
        draw_glow_circle(surface, head_col, hc, hr, layers=5)

        if self.shield_active:
            draw_glow_circle(surface, (0,140,255), hc, hr+4, layers=3)
        if self.bounce_available:
            draw_glow_circle(surface, (255,200,0), hc, hr+6, layers=2)

class Food:
    def __init__(self):
        self.pos   = (0, 0)
        self.pulse = 0.0
        self.respawn(set())

    def respawn(self, occupied):
        for _ in range(1000):
            x = random.randint(0, GRID_COLS-1)
            y = random.randint(0, GRID_ROWS-1)
            if (x, y) not in occupied:
                self.pos = (x, y)
                return

    def update(self, dt):
        self.pulse = (self.pulse + dt*4) % (math.pi*2)

    def draw(self, surface, ox=0, oy=0):
        cx = self.pos[0]*CELL_SIZE + CELL_SIZE//2 + ox
        cy = self.pos[1]*CELL_SIZE + CELL_SIZE//2 + oy
        r  = 6 + int(2*math.sin(self.pulse))
        draw_glow_circle(surface, COL_FOOD, (cx, cy), r, layers=4)

class PowerUpFood:
    def __init__(self, ptype, pos):
        self.ptype      = ptype
        self.pos        = pos
        self.colour     = POWERUP_COLOURS.get(ptype, COL_WHITE)
        self.pulse      = 0.0
        self.lifetime   = 7.0
        self.spawn_anim = 0.0

    @property
    def alive(self):
        return self.lifetime > 0

    def update(self, dt):
        self.pulse      += dt*3
        self.lifetime   -= dt
        self.spawn_anim  = min(1.0, self.spawn_anim+dt*3)

    def draw(self, surface, ox=0, oy=0):
        if not self.alive:
            return
        if self.lifetime < 2.0 and int(self.lifetime*6) % 2 == 0:
            return
        cx = self.pos[0]*CELL_SIZE + CELL_SIZE//2 + ox
        cy = self.pos[1]*CELL_SIZE + CELL_SIZE//2 + oy
        r  = int((7+3*math.sin(self.pulse)) * ease_out_cubic(self.spawn_anim))
        draw_glow_circle(surface, self.colour, (cx, cy), r, layers=5)

class ObstacleWall:
    def __init__(self, cells: List[Tuple[int,int]]):
        self.cells = cells
        self.alpha = 0.0

    def update(self, dt):
        self.alpha = min(1.0, self.alpha + dt*2)

    def draw(self, surface, ox=0, oy=0):
        a = int(self.alpha * 200)
        for (x, y) in self.cells:
            px   = x*CELL_SIZE + 1 + ox
            py   = y*CELL_SIZE + 1 + oy
            sz   = CELL_SIZE - 2
            rect = pygame.Rect(px, py, sz, sz)
            s    = pygame.Surface((sz, sz), pygame.SRCALPHA)
            pygame.draw.rect(s, (80,0,120,a), s.get_rect(), border_radius=3)
            surface.blit(s, rect.topleft)
            if self.alpha > 0.5:
                draw_glow_rect(surface, (120,0,200), rect, width=1, layers=2)

    @property
    def positions(self):
        return set(self.cells)

class ScreenShake:
    def __init__(self):
        self.intensity = 0.0
        self.offset_x  = 0.0
        self.offset_y  = 0.0

    def trigger(self, intensity=5.0):
        self.intensity = intensity

    def update(self, dt):
        if self.intensity > 0.1:
            self.offset_x  = random.uniform(-self.intensity, self.intensity)
            self.offset_y  = random.uniform(-self.intensity, self.intensity)
            self.intensity *= 0.85
        else:
            self.intensity = self.offset_x = self.offset_y = 0.0

    @property
    def offset(self):
        return (int(self.offset_x), int(self.offset_y))

class GameState:
    def __init__(self, game):
        self.game = game

    def handle_input(self, events): pass
    def update(self, dt):           pass
    def draw(self, surface):        pass

class MainMenuState(GameState):
    def __init__(self, game):
        super().__init__(game)
        cx = SCREEN_WIDTH//2
        self.buttons = [
            Button("START GAME",  cx, 320),
            Button("HOW TO PLAY", cx, 400),
            Button("HIGH SCORES", cx, 480),
            Button("ACHIEVEMENTS",cx, 560),
            Button("SETTINGS",    cx, 640),
        ]
        self.bg         = BackgroundEffect()
        self.title_glow = 0.0
        self._font_title= pygame.font.SysFont("consolas", 72, bold=True)
        self._font_sub  = pygame.font.SysFont("consolas", 18)

    def handle_input(self, events):
        for event in events:
            if event.type == pygame.QUIT:
                self.game.running = False
            for i, btn in enumerate(self.buttons):
                if btn.handle_event(event):
                    self.game.audio.play_sound("click")
                    targets = [STATE_GAMEPLAY, STATE_HOW_TO_PLAY,
                               STATE_HIGHSCORES, STATE_ACHIEVEMENTS, STATE_SETTINGS]
                    self.game.change_state(targets[i])

    def update(self, dt):
        self.bg.update(dt)
        self.title_glow += dt*2
        mouse = pygame.mouse.get_pos()
        for btn in self.buttons:
            old = btn.hovered
            btn.update(dt, mouse)
            if btn.hovered and not old:
                self.game.audio.play_sound("hover")

    def draw(self, surface):
        self.bg.draw(surface)
        gv    = int(180 + 75*math.sin(self.title_glow))
        glow  = (0, gv, int(gv*0.55))

        title = self._font_title.render("SNAKE EVOLUTION", True, (0, 0, 0))
        tx    = SCREEN_WIDTH//2 - title.get_width()//2
        ty    = 120
        gs    = pygame.Surface((title.get_width()+40, title.get_height()+40), pygame.SRCALPHA)
        pygame.draw.rect(gs, (*glow, 50), gs.get_rect(), border_radius=15)
        surface.blit(gs, (tx-20, ty-20), special_flags=pygame.BLEND_ADD)
        surface.blit(title, (tx, ty))

        sub = self._font_sub.render("Eat. Evolve. Survive.", True, (0, 0, 0))
        surface.blit(sub, (SCREEN_WIDTH//2 - sub.get_width()//2, ty+80))

        for btn in self.buttons:
            btn.draw(surface)

class HowToPlayState(GameState):
    def __init__(self, game):
        super().__init__(game)
        self.bg       = BackgroundEffect()
        self.back_btn = Button("BACK", SCREEN_WIDTH//2, 640)
        self.lines = [
            "CONTROLS:",
            "",
            "  Arrow Keys / WASD  -  Move snake",
            "  ESC                -  Pause game",
            "",
            "GOAL:",
            "  Eat food to grow and score points.",
            "  Every 5 foods triggers an EVOLUTION event.",
            "  Build combos by eating food quickly!",
            "",
            "POWER-UPS:",
            "  [Yellow]  Speed Boost   - Move 60% faster",
            "  [Purple]  Ghost Mode    - Pass through walls",
            "  [Blue]    Shield        - Survive one collision",
            "  [Gold]    Double Score  - 2x points",
            "  [Pink]    Magnet        - Auto-attract nearby food",
            "  [Cyan]    Shrink        - Trim 3 tail segments",
            "",
            "UPGRADE: Wall Bounce lets you survive 1 wall hit.",
        ]

    def handle_input(self, events):
        for event in events:
            if event.type == pygame.QUIT:
                self.game.running = False
            if self.back_btn.handle_event(event):
                self.game.audio.play_sound("click")
                self.game.change_state(STATE_MAIN_MENU)
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.game.change_state(STATE_MAIN_MENU)

    def update(self, dt):
        self.bg.update(dt)
        self.back_btn.update(dt, pygame.mouse.get_pos())

    def draw(self, surface):
        self.bg.draw(surface)
        font_t = pygame.font.SysFont("consolas", 48, bold=True)
        t = font_t.render("HOW TO PLAY", True, COL_CYAN)
        surface.blit(t, (SCREEN_WIDTH//2 - t.get_width()//2, 40))
        font  = pygame.font.SysFont("consolas", 17)
        pucol = {"[Yellow]":(255,220,0), "[Purple]":(180,0,255),
                 "[Blue]":(0,140,255),   "[Gold]":(255,215,0),
                 "[Pink]":(255,80,180),  "[Cyan]":(0,220,255)}
        y = 115
        for line in self.lines:
            col = COL_WHITE
            for tag, c in pucol.items():
                if tag in line:
                    col = c
                    break
            surface.blit(font.render(line, True, col), (120, y))
            y += 26
        self.back_btn.draw(surface)

class HighScoresState(GameState):
    def __init__(self, game):
        super().__init__(game)
        self.bg        = BackgroundEffect()
        self.back_btn  = Button("BACK",           SCREEN_WIDTH//2 - 170, 620, w=280, h=55)
        self.clear_btn = Button("CLEAR SCORES",   SCREEN_WIDTH//2 + 170, 620, w=280, h=55, font_size=22)
        self.confirm   = False
        self.confirm_btn_yes = Button("YES, CLEAR", SCREEN_WIDTH//2 - 120, 420, w=200, h=55, font_size=22)
        self.confirm_btn_no  = Button("CANCEL",     SCREEN_WIDTH//2 + 120, 420, w=200, h=55, font_size=22)
        self._font_title = pygame.font.SysFont("consolas", 48, bold=True)
        self._font_score = pygame.font.SysFont("consolas", 28)
        self._font_warn  = pygame.font.SysFont("consolas", 22, bold=True)

    def handle_input(self, events):
        for event in events:
            if event.type == pygame.QUIT:
                self.game.running = False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                if self.confirm:
                    self.confirm = False
                else:
                    self.game.change_state(STATE_MAIN_MENU)
            if not self.confirm:
                if self.back_btn.handle_event(event):
                    self.game.audio.play_sound("click")
                    self.game.change_state(STATE_MAIN_MENU)
                if self.clear_btn.handle_event(event):
                    self.game.audio.play_sound("click")
                    self.confirm = True
            else:
                if self.confirm_btn_yes.handle_event(event):
                    self.game.audio.play_sound("click")
                    self.game.highscores.clear()
                    self.confirm = False
                if self.confirm_btn_no.handle_event(event):
                    self.game.audio.play_sound("click")
                    self.confirm = False

    def update(self, dt):
        self.bg.update(dt)
        mouse = pygame.mouse.get_pos()
        if not self.confirm:
            self.back_btn.update(dt, mouse)
            self.clear_btn.update(dt, mouse)
        else:
            self.confirm_btn_yes.update(dt, mouse)
            self.confirm_btn_no.update(dt, mouse)

    def draw(self, surface):
        self.bg.draw(surface)
        t = self._font_title.render("HIGH SCORES", True, COL_GOLD)
        surface.blit(t, (SCREEN_WIDTH//2 - t.get_width()//2, 60))

        scores = self.game.highscores.scores
        for i in range(10):
            y   = 148 + i*43
            col = COL_NEON_GREEN if i == 0 else COL_WHITE
            txt = self._font_score.render(f"{i+1:>2}.  {scores[i]:>8}", True, col) \
                  if i < len(scores) else \
                  self._font_score.render(f"{i+1:>2}.  --------", True, (60,60,80))
            surface.blit(txt, (SCREEN_WIDTH//2 - txt.get_width()//2, y))

        if not self.confirm:
            self.back_btn.draw(surface)
            self.clear_btn.draw(surface)
        else:
            ov = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            ov.fill((0, 0, 0, 160))
            surface.blit(ov, (0, 0))
            warn = self._font_warn.render("Clear ALL high scores? This cannot be undone.", True, (255, 100, 100))
            surface.blit(warn, (SCREEN_WIDTH//2 - warn.get_width()//2, 360))
            self.confirm_btn_yes.draw(surface)
            self.confirm_btn_no.draw(surface)

class AchievementsState(GameState):
    def __init__(self, game):
        super().__init__(game)
        self.bg       = BackgroundEffect()
        self.back_btn = Button("BACK", SCREEN_WIDTH//2, 640)

    def handle_input(self, events):
        for event in events:
            if event.type == pygame.QUIT:
                self.game.running = False
            if self.back_btn.handle_event(event):
                self.game.audio.play_sound("click")
                self.game.change_state(STATE_MAIN_MENU)
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.game.change_state(STATE_MAIN_MENU)

    def update(self, dt):
        self.bg.update(dt)
        self.back_btn.update(dt, pygame.mouse.get_pos())

    def draw(self, surface):
        self.bg.draw(surface)
        ft = pygame.font.SysFont("consolas", 48, bold=True)
        t  = ft.render("ACHIEVEMENTS", True, COL_CYAN)
        surface.blit(t, (SCREEN_WIDTH//2 - t.get_width()//2, 30))
        fn = pygame.font.SysFont("consolas", 20, bold=True)
        fd = pygame.font.SysFont("consolas", 15)
        y  = 100
        for adef in ACHIEVEMENT_DEFS:
            unlocked = self.game.achievements.unlocked.get(adef["id"], False)
            col  = COL_NEON_GREEN if unlocked else (50,50,70)
            rect = pygame.Rect(180, y, 640, 50)
            draw_rounded_rect(surface, (15,15,35), rect, radius=8, alpha=200)
            if unlocked:
                draw_glow_rect(surface, COL_NEON_GREEN, rect, width=1, layers=2)
            else:
                pygame.draw.rect(surface, (40,40,60), rect, width=1, border_radius=8)
            icon = "★" if unlocked else "☆"
            surface.blit(fn.render(f"{icon} {adef['name']}", True, col), (rect.x+15, rect.y+6))
            dcol = (180,255,200) if unlocked else (80,80,100)
            surface.blit(fd.render(adef["desc"], True, dcol), (rect.x+15, rect.y+28))
            y += 58
        self.back_btn.draw(surface)

class SettingsState(GameState):
    def __init__(self, game):
        super().__init__(game)
        self.bg       = BackgroundEffect()
        self.back_btn = Button("BACK", SCREEN_WIDTH//2, 640)
        cx = SCREEN_WIDTH//2
        self.music_slider = Slider(cx-150, 180, 300, game.settings.get("music_volume"), "Music Volume")
        self.sfx_slider   = Slider(cx-150, 270, 300, game.settings.get("sfx_volume"),   "SFX Volume")
        self.shake_on     = game.settings.get("screen_shake")
        self.particle_idx = ["LOW","MEDIUM","HIGH"].index(game.settings.get("particle_density"))
        self.diff_idx     = ["EASY","NORMAL","HARD","INSANE"].index(game.settings.get("difficulty"))
        self.shake_btn    = Button("SHAKE: ON" if self.shake_on else "SHAKE: OFF", cx, 380, w=300, h=50, font_size=20)
        self.particle_btn = Button(f"PARTICLES: {['LOW','MEDIUM','HIGH'][self.particle_idx]}", cx, 450, w=300, h=50, font_size=20)
        self.diff_btn     = Button(f"DIFFICULTY: {['EASY','NORMAL','HARD','INSANE'][self.diff_idx]}", cx, 520, w=300, h=50, font_size=20)

    def handle_input(self, events):
        for event in events:
            if event.type == pygame.QUIT:
                self.game.running = False
            self.music_slider.handle_event(event)
            self.sfx_slider.handle_event(event)
            if self.back_btn.handle_event(event):
                self.game.audio.play_sound("click")
                self._save()
                self.game.change_state(STATE_MAIN_MENU)
            if self.shake_btn.handle_event(event):
                self.shake_on = not self.shake_on
                self.shake_btn.text = "SHAKE: ON" if self.shake_on else "SHAKE: OFF"
            if self.particle_btn.handle_event(event):
                self.particle_idx = (self.particle_idx+1) % 3
                self.particle_btn.text = f"PARTICLES: {['LOW','MEDIUM','HIGH'][self.particle_idx]}"
            if self.diff_btn.handle_event(event):
                self.diff_idx = (self.diff_idx+1) % 4
                self.diff_btn.text = f"DIFFICULTY: {['EASY','NORMAL','HARD','INSANE'][self.diff_idx]}"
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self._save()
                self.game.change_state(STATE_MAIN_MENU)

    def _save(self):
        self.game.settings.set("music_volume",    self.music_slider.value)
        self.game.settings.set("sfx_volume",      self.sfx_slider.value)
        self.game.settings.set("screen_shake",    self.shake_on)
        self.game.settings.set("particle_density",["LOW","MEDIUM","HIGH"][self.particle_idx])
        self.game.settings.set("difficulty",      ["EASY","NORMAL","HARD","INSANE"][self.diff_idx])
        self.game.settings.save()
        self.game.audio.update_volumes(self.music_slider.value/100.0, self.sfx_slider.value/100.0)

    def update(self, dt):
        self.bg.update(dt)
        mouse = pygame.mouse.get_pos()
        for w in [self.back_btn, self.shake_btn, self.particle_btn, self.diff_btn]:
            w.update(dt, mouse)
        self.game.audio.update_volumes(self.music_slider.value/100.0, self.sfx_slider.value/100.0)

    def draw(self, surface):
        self.bg.draw(surface)
        ft = pygame.font.SysFont("consolas", 48, bold=True)
        t  = ft.render("SETTINGS", True, COL_CYAN)
        surface.blit(t, (SCREEN_WIDTH//2 - t.get_width()//2, 60))
        self.music_slider.draw(surface)
        self.sfx_slider.draw(surface)
        for w in [self.shake_btn, self.particle_btn, self.diff_btn, self.back_btn]:
            w.draw(surface)

class UpgradeState(GameState):
    UPGRADES = [
        {"name": "SPEED+",    "desc": "Base speed +1",         "key": "speed_up"},
        {"name": "LENGTH+",   "desc": "Grow 3 extra segments", "key": "grow"},
        {"name": "SCORE+",    "desc": "+100 bonus score",      "key": "score"},
        {"name": "SHIELD",    "desc": "Gain a one-hit shield", "key": "shield"},
        {"name": "WALL BOUNCE","desc":"Survive 1 wall hit",    "key": "bounce"},
    ]

    def __init__(self, game):
        super().__init__(game)
        self.choices = random.sample(self.UPGRADES, 3)
        cx = SCREEN_WIDTH//2
        self.buttons = [Button(f"{c['name']}: {c['desc']}", cx, 300+i*90, w=520, h=70, font_size=20)
                        for i, c in enumerate(self.choices)]
        self.anim_t = 0.0

    def handle_input(self, events):
        for event in events:
            if event.type == pygame.QUIT:
                self.game.running = False
            for i, btn in enumerate(self.buttons):
                if btn.handle_event(event):
                    self.game.audio.play_sound("click")
                    self._apply(self.choices[i]["key"])
                    self.game.change_state(STATE_GAMEPLAY)

    def _apply(self, key):
        gs = self.game.gameplay_state
        if not gs:
            return
        if   key == "speed_up": gs.snake.base_speed = min(20, gs.snake.base_speed+1)
        elif key == "grow":     gs.snake.grow(3)
        elif key == "score":    gs.score += 100
        elif key == "shield":   gs.snake.shield_active = True
        elif key == "bounce":   gs.snake.bounce_available = True

    def update(self, dt):
        self.anim_t = min(1.0, self.anim_t+dt*3)
        mouse = pygame.mouse.get_pos()
        for btn in self.buttons:
            btn.update(dt, mouse)

    def draw(self, surface):
        if self.game.gameplay_state:
            self.game.gameplay_state.draw(surface)
        ov = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        ov.fill((0,0,0,185))
        surface.blit(ov, (0,0))
        alpha = int(255*ease_out_cubic(self.anim_t))
        ft = pygame.font.SysFont("consolas", 48, bold=True)
        t  = ft.render("EVOLUTION!", True, COL_NEON_GREEN)
        t.set_alpha(alpha)
        surface.blit(t, (SCREEN_WIDTH//2 - t.get_width()//2, 160))
        sub = pygame.font.SysFont("consolas", 20).render("Choose an upgrade:", True, COL_WHITE)
        sub.set_alpha(alpha)
        surface.blit(sub, (SCREEN_WIDTH//2 - sub.get_width()//2, 230))
        for btn in self.buttons:
            btn.draw(surface)

class PauseState(GameState):
    def __init__(self, game):
        super().__init__(game)
        cx = SCREEN_WIDTH//2
        self.buttons = [
            Button("RESUME",    cx, 280),
            Button("RESTART",   cx, 360),
            Button("MAIN MENU", cx, 440),
            Button("QUIT",      cx, 520),
        ]

    def handle_input(self, events):
        for event in events:
            if event.type == pygame.QUIT:
                self.game.running = False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.game.change_state(STATE_GAMEPLAY)
            for i, btn in enumerate(self.buttons):
                if btn.handle_event(event):
                    self.game.audio.play_sound("click")
                    [STATE_GAMEPLAY, STATE_GAMEPLAY, STATE_MAIN_MENU, None][i]
                    if   i == 0: self.game.change_state(STATE_GAMEPLAY)
                    elif i == 1: self.game.change_state(STATE_GAMEPLAY, fresh=True)
                    elif i == 2: self.game.change_state(STATE_MAIN_MENU)
                    elif i == 3: self.game.running = False

    def update(self, dt):
        mouse = pygame.mouse.get_pos()
        for btn in self.buttons:
            btn.update(dt, mouse)

    def draw(self, surface):
        if self.game.gameplay_state:
            self.game.gameplay_state.draw(surface)
        ov = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        ov.fill((0,0,0,160))
        surface.blit(ov, (0,0))
        ft = pygame.font.SysFont("consolas", 56, bold=True)
        t  = ft.render("PAUSED", True, COL_CYAN)
        surface.blit(t, (SCREEN_WIDTH//2 - t.get_width()//2, 150))
        for btn in self.buttons:
            btn.draw(surface)

class GameOverState(GameState):
    def __init__(self, game):
        super().__init__(game)
        cx = SCREEN_WIDTH//2
        self.buttons = [Button("RESTART", cx, 450), Button("MAIN MENU", cx, 530)]
        self.anim_t  = 0.0
        gs           = game.gameplay_state
        self.score   = gs.score if gs else 0
        self.length  = gs.snake.length if gs else 0
        self.max_combo = gs.combo.max_combo if gs else 0
        self.high    = game.highscores.best
        game.highscores.add(self.score)
        self.new_high = self.score > self.high and self.score > 0

    def handle_input(self, events):
        for event in events:
            if event.type == pygame.QUIT:
                self.game.running = False
            for i, btn in enumerate(self.buttons):
                if btn.handle_event(event):
                    self.game.audio.play_sound("click")
                    if i == 0: self.game.change_state(STATE_GAMEPLAY, fresh=True)
                    else:      self.game.change_state(STATE_MAIN_MENU)

    def update(self, dt):
        self.anim_t = min(1.0, self.anim_t+dt*2)
        mouse = pygame.mouse.get_pos()
        for btn in self.buttons:
            btn.update(dt, mouse)

    def draw(self, surface):
        surface.fill(COL_BG)
        alpha = int(255*ease_out_cubic(self.anim_t))
        font_big = pygame.font.SysFont("consolas", 64, bold=True)
        font     = pygame.font.SysFont("consolas", 28)
        font_sm  = pygame.font.SysFont("consolas", 22)

        def blit_alpha(surf, y):
            surf.set_alpha(alpha)
            surface.blit(surf, (SCREEN_WIDTH//2 - surf.get_width()//2, y))

        blit_alpha(font_big.render("GAME OVER", True, (255,60,60)), 110)
        blit_alpha(font.render(f"Score: {self.score}", True, COL_WHITE), 230)
        blit_alpha(font.render(f"High Score: {self.game.highscores.best}", True, COL_GOLD), 275)
        blit_alpha(font_sm.render(f"Length: {self.length}   Best Combo: x{self.max_combo}", True, (160,200,255)), 320)
        if self.new_high:
            blit_alpha(pygame.font.SysFont("consolas",24,bold=True).render("NEW HIGH SCORE!", True, COL_NEON_GREEN), 360)
        for btn in self.buttons:
            btn.draw(surface)

class GameplayState(GameState):
    def __init__(self, game):
        super().__init__(game)
        self.snake    = Snake()
        self.food     = Food()
        self.powerups: List[PowerUpFood]  = []
        self.walls:    List[ObstacleWall] = []
        self.particles = ParticleSystem(game.settings.particle_multiplier)
        self.shake    = ScreenShake()
        self.combo    = ComboDisplay()

        self.score          = 0
        self.foods_eaten    = 0
        self.evolution_count= 0
        self.survive_time   = 0.0
        self.score_popups: List[ScorePopup] = []
        self.powerup_timer  = 0.0
        self.wall_timer     = 0.0
        self.game_over_triggered = False
        self.death_anim     = 0.0

        speed_mult, self.powerup_interval, self.wall_density = game.settings.difficulty_tuple
        self.snake.base_speed *= speed_mult

        self.food.respawn(set(self.snake.segments))
        self._generate_walls()

        self._font_hud   = pygame.font.SysFont("consolas", 24, bold=True)
        self._font_hud_sm= pygame.font.SysFont("consolas", 18)
        self._font_ind   = pygame.font.SysFont("consolas", 16, bold=True)
        self._font_evo   = pygame.font.SysFont("consolas", 12)

    def _all_wall_cells(self) -> set:
        s = set()
        for w in self.walls:
            s |= w.positions
        return s

    def _occupied_set(self) -> set:
        occ = set(self.snake.segments)
        occ.add(self.food.pos)
        for pu in self.powerups:
            occ.add(pu.pos)
        occ |= self._all_wall_cells()
        return occ

    def handle_input(self, events):
        for event in events:
            if event.type == pygame.QUIT:
                self.game.running = False
            if event.type == pygame.KEYDOWN:
                if   event.key == pygame.K_ESCAPE:                      self.game.change_state(STATE_PAUSE)
                elif event.key in (pygame.K_UP,    pygame.K_w):         self.snake.set_direction(DIR_UP)
                elif event.key in (pygame.K_DOWN,  pygame.K_s):         self.snake.set_direction(DIR_DOWN)
                elif event.key in (pygame.K_LEFT,  pygame.K_a):         self.snake.set_direction(DIR_LEFT)
                elif event.key in (pygame.K_RIGHT, pygame.K_d):         self.snake.set_direction(DIR_RIGHT)

    def update(self, dt):
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
        self.combo.update(dt)

        for pu in self.powerups:
            pu.update(dt)
        self.powerups = [pu for pu in self.powerups if pu.alive]

        self.powerup_timer += dt
        if self.powerup_timer >= self.powerup_interval:
            self.powerup_timer = 0
            self._spawn_powerup()

        self.wall_timer += dt
        if self.wall_timer >= 45:
            self.wall_timer = 0
            self._add_walls()
        for w in self.walls:
            w.update(dt)

        for sp in self.score_popups:
            sp.update(dt)
        self.score_popups = [sp for sp in self.score_popups if sp.alive]

        if self.snake.magnet_timer > 0:
            self._apply_magnet()

        stepped = self.snake.update(dt)
        if stepped:
            self._check_collisions()

        time_bonus = self.survive_time / 120.0
        if self.snake.speed_boost_timer <= 0:
            self.snake.speed = min(self.snake.base_speed + time_bonus, 20.0)

        self.game.achievements.check(
            self.score, self.snake.length, self.snake.speed,
            self.survive_time, self.foods_eaten, self.combo.max_combo)
        self.game.achievements.update(dt)

    def _apply_magnet(self):
        hx, hy = self.snake.head
        fx, fy = self.food.pos
        dx, dy = fx-hx, fy-hy
        dist   = math.sqrt(dx*dx + dy*dy)
        if 0 < dist <= 6:
            nx = fx + (-1 if dx > 0 else 1) if abs(dx) > abs(dy) else fx
            ny = fy + (-1 if dy > 0 else 1) if abs(dy) >= abs(dx) else fy
            nx = clamp(nx, 0, GRID_COLS-1)
            ny = clamp(ny, 0, GRID_ROWS-1)
            occ = self._occupied_set()
            occ.discard(self.food.pos)
            if (nx, ny) not in occ:
                self.food.pos = (int(nx), int(ny))

    def _check_collisions(self):
        if self.snake.check_wall_collision():
            if self.snake.bounce_available:
                self.snake.wall_bounce()
                if self.game.settings.get("screen_shake"):
                    self.shake.trigger(5)
                self.combo.reset()
            else:
                self._die()
            return

        if self.snake.check_self_collision():
            if self.snake.shield_active:
                self.snake.shield_active = False
                self.shake.trigger(4) if self.game.settings.get("screen_shake") else None
                self.combo.reset()
            else:
                self._die()
            return

        wall_cells = self._all_wall_cells()
        if self.snake.head in wall_cells:
            if self.snake.ghost_timer > 0:
                pass
            elif self.snake.shield_active:
                self.snake.shield_active = False
                self.walls = [w for w in self.walls if self.snake.head not in w.positions]
                self.shake.trigger(4) if self.game.settings.get("screen_shake") else None
                self.combo.reset()
            else:
                self._die()
            return

        if self.snake.head == self.food.pos:
            self.game.audio.play_sound("eat")
            self.snake.grow(1)
            self.snake.head_scale = 1.4
            self.combo.feed()
            mult      = self.combo.multiplier()
            if self.snake.double_score_timer > 0:
                mult *= 2
            score_val = 10 * mult
            self.score += score_val
            self.foods_eaten += 1

            if self.combo.combo > 1:
                self.game.audio.play_sound("combo")

            cx = self.food.pos[0]*CELL_SIZE + CELL_SIZE//2
            cy = self.food.pos[1]*CELL_SIZE + CELL_SIZE//2
            self.particles.emit(cx, cy, COL_FOOD, count=12, speed=120, life=0.6)
            col = COL_GOLD if mult > 1 else COL_FOOD
            self.score_popups.append(ScorePopup(cx, cy-10, score_val, col))
            if self.game.settings.get("screen_shake"):
                self.shake.trigger(3)
            self.food.respawn(self._occupied_set())

            if self.foods_eaten % 5 == 0:
                self.evolution_count += 1
                self.game.achievements.evolution_count = self.evolution_count
                self.score += 50
                self.game.audio.play_sound("evolve")
                hx = self.snake.head[0]*CELL_SIZE + CELL_SIZE//2
                hy = self.snake.head[1]*CELL_SIZE + CELL_SIZE//2
                self.particles.emit(hx, hy, COL_NEON_GREEN, count=30, speed=200, life=1.0, size=4)
                self.game.change_state(STATE_UPGRADE)

        for pu in self.powerups[:]:
            if self.snake.head == pu.pos:
                self.game.audio.play_sound("powerup")
                self.snake.apply_powerup(pu.ptype)
                if pu.ptype == "ghost":  self.game.achievements.ghost_uses  += 1
                if pu.ptype == "magnet": self.game.achievements.magnet_uses += 1
                sv = 25 * (2 if self.snake.double_score_timer > 0 else 1)
                self.score += sv
                cx = pu.pos[0]*CELL_SIZE + CELL_SIZE//2
                cy = pu.pos[1]*CELL_SIZE + CELL_SIZE//2
                self.particles.emit(cx, cy, pu.colour, count=20, speed=150, life=0.8, size=4)
                self.score_popups.append(ScorePopup(cx, cy-10, sv, pu.colour))
                self.powerups.remove(pu)

    def _spawn_powerup(self):
        occ   = self._occupied_set()
        ptype = random.choice(list(POWERUP_COLOURS.keys()))
        for _ in range(50):
            x = random.randint(0, GRID_COLS-1)
            y = random.randint(0, GRID_ROWS-1)
            if (x,y) not in occ:
                self.powerups.append(PowerUpFood(ptype, (x,y)))
                return

    def _generate_walls(self):
        self.walls.clear()
        self._add_walls(initial=True)

    def _add_walls(self, initial=False):
        occ   = self._occupied_set()
        for seg in self.snake.segments:
            occ.add(seg)
        hx, hy = self.snake.head
        dx, dy = self.snake.direction
        safe   = {(hx+dx*i, hy+dy*i) for i in range(1,5)}

        density= self.wall_density * (1.0 if initial else 0.3)
        target = max(1, int(GRID_COLS * GRID_ROWS * density))
        placed = 0
        attempts = 0
        while placed < target and attempts < 600:
            attempts += 1
            length     = random.randint(3, 6)
            horizontal = random.choice([True, False])
            if horizontal:
                sx = random.randint(0, GRID_COLS-length)
                sy = random.randint(0, GRID_ROWS-1)
                cells = [(sx+i, sy) for i in range(length)]
            else:
                sx = random.randint(0, GRID_COLS-1)
                sy = random.randint(0, GRID_ROWS-length)
                cells = [(sx, sy+i) for i in range(length)]
            if any(c in occ or c in safe for c in cells):
                continue
            self.walls.append(ObstacleWall(cells))
            for c in cells:
                occ.add(c)
            placed += length

    def _die(self):
        if self.game_over_triggered:
            return
        self.game_over_triggered = True
        self.snake.alive = False
        self.game.audio.play_sound("gameover")
        if self.game.settings.get("screen_shake"):
            self.shake.trigger(12)
        for sx, sy in self.snake.segments:
            cx = sx*CELL_SIZE + CELL_SIZE//2
            cy = sy*CELL_SIZE + CELL_SIZE//2
            self.particles.emit(cx, cy, COL_SNAKE_HEAD, count=5, speed=180, life=1.2, size=3, gravity=60)

    def draw(self, surface):
        ox, oy = self.shake.offset
        surface.fill(COL_BG)
        for x in range(0, SCREEN_WIDTH, CELL_SIZE):
            pygame.draw.line(surface, COL_GRID, (x+ox, 0), (x+ox, SCREEN_HEIGHT), 1)
        for y in range(0, SCREEN_HEIGHT, CELL_SIZE):
            pygame.draw.line(surface, COL_GRID, (0, y+oy), (SCREEN_WIDTH, y+oy), 1)

        saved = surface.get_clip()
        surface.set_clip(surface.get_rect())

        for w in self.walls:
            w.draw(surface, ox, oy)
        self.food.draw(surface, ox, oy)
        for pu in self.powerups:
            pu.draw(surface, ox, oy)
        if not self.game_over_triggered:
            self.snake.draw(surface, self.particles, ox, oy)
        self.particles.draw(surface, ox, oy)

        surface.set_clip(saved)

        for sp in self.score_popups:
            sp.draw(surface)
        self._draw_ui(surface)
        self.combo.draw(surface)
        self.game.achievements.draw(surface)

        if self.game_over_triggered:
            alpha = min(200, int(self.death_anim*150))
            ov    = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            ov.fill((0,0,0,alpha))
            surface.blit(ov, (0,0))

    def _draw_ui(self, surface):
        surface.blit(self._font_hud.render(f"Score: {self.score}", True, COL_WHITE), (15, 10))
        surface.blit(self._font_hud.render(f"Length: {self.snake.length}", True, COL_WHITE), (15, 38))
        surface.blit(self._font_hud_sm.render(f"Best: {self.game.highscores.best}", True, (120,120,160)), (15, 66))

        indicators = []
        if self.snake.speed_boost_timer  > 0: indicators.append(("SPD", POWERUP_COLOURS["speed"]))
        if self.snake.ghost_timer        > 0: indicators.append(("GHO", POWERUP_COLOURS["ghost"]))
        if self.snake.double_score_timer > 0: indicators.append(("x2",  POWERUP_COLOURS["double"]))
        if self.snake.magnet_timer       > 0: indicators.append(("MAG", POWERUP_COLOURS["magnet"]))
        if self.snake.shield_active:          indicators.append(("SHD", POWERUP_COLOURS["shield"]))
        if self.snake.bounce_available:       indicators.append(("BNC", COL_GOLD))

        for i, (label, col) in enumerate(indicators):
            x    = SCREEN_WIDTH - 70*(i+1) - 10
            rect = pygame.Rect(x, 10, 60, 28)
            draw_rounded_rect(surface, (10,10,30), rect, radius=6, alpha=200)
            draw_glow_rect(surface, col, rect, width=1, layers=2)
            t = self._font_ind.render(label, True, col)
            surface.blit(t, (rect.centerx - t.get_width()//2, rect.centery - t.get_height()//2))

        progress = self.foods_eaten % 5
        bw, bh   = 150, 10
        bx       = SCREEN_WIDTH//2 - bw//2
        by       = 12
        pygame.draw.rect(surface, (30,30,60), (bx, by, bw, bh), border_radius=4)
        fill = int(bw * progress / 5)
        if fill > 0:
            pygame.draw.rect(surface, COL_NEON_GREEN, (bx, by, fill, bh), border_radius=4)
        el = self._font_evo.render(f"Evolution {self.evolution_count}", True, (100,200,150))
        surface.blit(el, (SCREEN_WIDTH//2 - el.get_width()//2, by+14))

class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Snake Evolution")
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        self.clock  = pygame.time.Clock()
        self.running= True

        self.settings    = SettingsManager()
        self.audio       = AudioManager()
        self.audio.update_volumes(self.settings.get("music_volume")/100.0,
                                  self.settings.get("sfx_volume")/100.0)
        self.highscores  = HighScoreManager()
        self.achievements= AchievementManager()

        self.gameplay_state:    Optional[GameplayState] = None
        self.current_state:     GameState = MainMenuState(self)
        self.current_state_name: str      = STATE_MAIN_MENU

        self.audio.start_music()

    def change_state(self, state_name: str, fresh: bool = False):
        if   state_name == STATE_MAIN_MENU:
            self.gameplay_state = None
            self.current_state  = MainMenuState(self)
        elif state_name == STATE_GAMEPLAY:
            if self.gameplay_state is None or fresh:
                self.gameplay_state = GameplayState(self)
            self.current_state = self.gameplay_state
        elif state_name == STATE_PAUSE:       self.current_state = PauseState(self)
        elif state_name == STATE_GAME_OVER:   self.current_state = GameOverState(self)
        elif state_name == STATE_UPGRADE:     self.current_state = UpgradeState(self)
        elif state_name == STATE_HOW_TO_PLAY: self.current_state = HowToPlayState(self)
        elif state_name == STATE_SETTINGS:    self.current_state = SettingsState(self)
        elif state_name == STATE_ACHIEVEMENTS:self.current_state = AchievementsState(self)
        elif state_name == STATE_HIGHSCORES:  self.current_state = HighScoresState(self)
        self.current_state_name = state_name

    def run(self):
        while self.running:
            dt     = min(self.clock.tick(FPS)/1000.0, 0.05)
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
    Game().run()
