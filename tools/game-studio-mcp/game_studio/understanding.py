"""Natural-language game-request understanding.

This module is deliberately deterministic and dependency-free. It does not try
to replace a language model; it gives the agent a reproducible first pass that

* keeps the user's original wording,
* recognises common English, Roman Urdu and Urdu game vocabulary,
* separates explicit requirements from implied, technical, optional and
  unresolved ones,
* surfaces conflicts and the small number of questions that materially change
  the architecture.

Every extracted concept carries the matched phrase and character offsets so a
later requirement can be traced back to what the user actually said.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# --------------------------------------------------------------------------
# Vocabulary
# --------------------------------------------------------------------------
# canonical -> list of surface forms. Matching is case-insensitive and uses
# Unicode-aware word boundaries; longer phrases win over shorter ones.
LEXICON: dict[str, dict[str, list[str]]] = {
    "dimension": {
        "3d": ["3d", "3-d", "three dimensional", "three-dimensional", "تھری ڈی"],
        "2d": ["2d", "2-d", "two dimensional", "two-dimensional", "ٹو ڈی"],
        "2.5d": ["2.5d", "2.5 d", "isometric", "top down", "top-down", "آئیسومیٹرک"],
        "first-person": ["first person", "first-person", "fps view", "فرسٹ پرسن"],
        "third-person": ["third person", "third-person", "تھرڈ پرسن"],
    },
    "genre": {
        "racing": ["racing game", "racing", "race game", "car race", "gari ki race",
                   "gaari ki race", "ریسنگ", "ریس"],
        "adventure": ["adventure game", "adventure", "exploration game", "مہم جوئی",
                      "ایڈونچر"],
        "platformer": ["platformer", "platform game", "jump game", "jumping game",
                       "پلیٹ فارمر"],
        "shooter": ["shooter", "shooting game", "fps", "first person shooter",
                    "third person shooter", "شوٹر"],
        "action": ["action game", "action", "ایکشن"],
        "rpg": ["role playing game", "role-playing game", "rpg", "آر پی جی"],
        "puzzle": ["puzzle game", "puzzle", "paheli", "پہیلی", "پزل"],
        "horror": ["horror game", "horror", "scary game", "darawana khel", "ڈراونا",
                   "ہارر"],
        "survival": ["survival game", "survival", "zinda rehne", "زندہ رہنے", "سرائیوول"],
        "fighting": ["fighting game", "fighting", "fight game", "ladai ka khel",
                     "لڑائی", "فائٹنگ"],
        "strategy": ["strategy game", "strategy", "rts", "حکمت عملی", "اسٹریٹجی"],
        "sports": ["sports game", "sports", "football game", "cricket game", "soccer game",
                   "کھیلوں", "اسپورٹس"],
        "simulation": ["simulation game", "simulation", "simulator", "سمولیشن"],
        "tower-defense": ["tower defense", "tower defence", "ٹاور ڈیفنس"],
        "open-world": ["open world", "open-world", "کھلی دنیا"],
        "battle-royale": ["battle royale", "battle-royale", "بیٹل روئیل"],
        "idle": ["idle game", "clicker game", "idle", "آئڈل"],
        "rhythm": ["rhythm game", "music game", "rhythm", "ردم"],
        "educational": ["educational game", "learning game", "educational", "تعلیمی"],
    },
    "character": {
        "monkey": ["monkey", "ape", "chimpanzee", "bandar", "bandaroon", "بندر", "بندروں"],
        "human": ["human", "person", "player character", "insaan", "انسان"],
        "robot": ["robot", "mech", "روبوٹ"],
        "dragon": ["dragon", "azhdaha", "اژدہا", "ڈریگن"],
        "knight": ["knight", "نائٹ"],
        "soldier": ["soldier", "sipahi", "سپاہی", "سولجر"],
        "zombie": ["zombie", "undead", "زومبی"],
        "animal": ["animal", "janwar", "جانور"],
        "car": ["car", "vehicle", "gaari", "gari", "گاڑی", "کار", "bike", "motorcycle"],
        "ship": ["spaceship", "ship", "starship", "خلائی جہاز"],
    },
    "environment": {
        "jungle": ["jungle", "rainforest", "ped", "darakht", "درخت", "جنگل"],
        "forest": ["forest", "woods", "بن"],
        "desert": ["desert", "registan", "ریگستان", "صحرا"],
        "city": ["city", "town", "shehar", "شہر"],
        "space": ["space", "outer space", "خلا", "space station"],
        "underwater": ["underwater", "ocean", "sea", "samundar", "سمندر",
                       "پانی کے نیچے"],
        "mountain": ["mountain", "pahar", "پہاڑ"],
        "snow": ["snow", "snowy", "barf", "برف"],
        "medieval": ["medieval", "middle ages", "قرون وسطی"],
        "cyberpunk": ["cyberpunk", "سائبر پنک"],
        "village": ["village", "gaon", "گاؤں"],
        "dungeon": ["dungeon", "tunnel", " underground", "تہہ خانہ"],
        "island": ["island", "جزیرہ"],
    },
    "style": {
        "realistic": ["realistic", "photorealistic", "photo-realistic", "real",
                      "haqiqi", "حقیقت پسندانہ", "ریئلسٹک"],
        "low-poly": ["low poly", "low-poly", "lowpoly", "لو پولی"],
        "cartoon": ["cartoon", "cartoonish", "کارٹون"],
        "stylized": ["stylized", "stylised", "اسٹائلائزڈ"],
        "pixel-art": ["pixel art", "pixel-art", "pixel", "پکسل"],
        "anime": ["anime", "manga", "انیمے", "اینمی"],
        "cel-shaded": ["cel shaded", "cel-shaded", "toon shaded", "سیل شیڈڈ"],
        "retro": ["retro", "8 bit", "16 bit", "ریٹرو"],
        "hand-painted": ["hand painted", "hand-painted", "ہاتھ سے پینٹ"],
    },
    "mechanic": {
        "multiplayer": ["multiplayer", "multi player", "multi-player", "online play",
                        "co-op", "coop", "co op", "دو کھلاڑی", "ملٹی پلیئر"],
        "ai-opponents": ["ai opponents", "ai opponent", "ai enemies", "computer players",
                         "bots", "dushman ai", "اے آئی دشمن"],
        "drifting": ["drifting", "drift", "ڈرفٹنگ"],
        "driving": ["driving", "drive", "chalana", "چلانا"],
        "jumping": ["jumping", "jump", "uchal", "چھلانگ"],
        "climbing": ["climbing", "climb", "charhna", "charh", "chadh", "چڑھنا", "چڑھ"],
        "swimming": ["swimming", "swim", "tairna", "tair", "تیرنا", "تیر"],
        "shooting": ["shooting", "shoot", "goli chalana", "گولی چلانا"],
        "weapons": ["guns", "gun", "weapons", "weapon", "firearms", "hathyar",
                    "hathiyar", "hathiyaar", "bandooq", "bandook", "ہتھیار", "بندوق"],
        "violence": ["violence", "blood", "gore", "تشدد", "خون"],
        "combat": ["combat", "melee", "sword fighting", "talwar", "تلوار", "لڑائی"],
        "enemies": ["enemies", "enemy", "dushman", "دشمن"],
        "inventory": ["inventory", "backpack", "بیک پیک"],
        "crafting": ["crafting", "craft", "بنانا"],
        "save-system": ["save game", "save system", "save progress", "محفوظ کریں"],
        "quests": ["quests", "quest", "missions", "mission", "مشن"],
        "stealth": ["stealth", "chupke", "چپکے"],
        "laps": ["laps", "lap system", "لیپ"],
        "checkpoints": ["checkpoints", "checkpoint", "چیک پوائنٹ"],
        "collectibles": ["collectibles", "collect coins", "coins", "sikke", "سکے",
                         "banana", "bananas", "کیلا", "کیلے"],
        "health": ["health bar", "health system", "hp", "ہیلتھ"],
        "score": ["score", "points", "سکور"],
        "procedural": ["procedural", "procedurally generated", "randomly generated",
                       "پروسیجرل"],
        "weather": ["weather", "rain", "barish", "بارش", "موسم"],
        "day-night": ["day night", "day-night", "din raat", "دن رات"],
        "ranking": ["ranking", "leaderboard", "ranked", "لیڈر بورڈ"],
        "trading": ["trading", "economy", "shop", "دکان"],
        "dialogue": ["dialogue", "dialog", "conversation", "گفتگو"],
    },
    "platform": {
        "pc": ["pc", "windows", "desktop", "steam", "کمپیوٹر"],
        "mobile": ["mobile", "android", "ios", "phone", "tablet", "موبائل", "اینڈرائیڈ"],
        "console": ["console", "playstation", "xbox", "nintendo switch", "کنسول"],
        "web": ["web game", "browser game", "html5", "webgl", "ویب"],
        "vr": ["vr", "virtual reality", "وی آر"],
    },
    "engine": {
        "unity": ["unity", "یونٹی"],
        "unreal": ["unreal engine", "unreal", "ue5", "ue4", "یونریل", "انریل"],
        "godot": ["godot", "گوڈوٹ"],
        "gamemaker": ["gamemaker", "game maker", "گیم میکر"],
        "defold": ["defold", "ڈیفولڈ"],
        "construct": ["construct 3", "construct", "کنسرٹکٹ"],
        "love2d": ["love2d", "love 2d", "löve"],
        "threejs": ["three.js", "threejs", "تھری جے ایس"],
    },
}

# Words that only occur in Roman Urdu, used for language reporting.
ROMAN_URDU_HINTS = {
    "banao", "bana", "banaiye", "banade", "bnana", "bnayen", "khel", "khail",
    "bandar", "bandaroon", "gaari", "gari", "jungle", "pahar", "shehar", "gaon",
    "dushman", "ladai", "paheli", "haqiqi", "barish", "sikke", "talwar", "sipahi",
    "janwar", "samundar", "registan", "chalana", "uchal", "charhna", "tairna",
    "chupke", "zinda", "din raat", "goli", "bina", "ke baghair", "ke bina",
    "charh", "tair", "ped", "darakht", "pani", "bhai",
}
URDU_HINTS = {"بنائیں", "بنانا", "کھیل", "گیم", "بندر", "گاڑی", "جنگل", "دشمن"}

NEGATION_MARKERS = [
    "without", "no ", "not ", "don't want", "dont want", "do not want", "avoid",
    "exclude", "never", "bina", "baghair", "ke baghair", "ke bina", "بغیر", "نہیں",
    "مت", "بغیر",
]
NEGATION_SUFFIX = ["ke baghair", "ke bina", "nahi chahiye", "nahin chahiye",
                   "نہیں چاہیے", "بغیر"]

# --------------------------------------------------------------------------
# Genre knowledge: implied systems, optional ideas and QA tests
# --------------------------------------------------------------------------
GENRE_TEMPLATES: dict[str, dict] = {
    "racing": {
        "systems": [
            ("Vehicle physics", "Engine-specific wheel/vehicle physics with mass, drag and "
                                "tyre grip."),
            ("Steering, throttle and brake input", "Map input actions to vehicle controls with "
                                                   "dead-zone and remapping support."),
            ("Chase camera", "Follow camera with smoothing, speed FOV and collision avoidance."),
            ("Track collision and boundaries", "Solid collision on track edges, barriers and "
                                              "terrain; no pass-through."),
            ("Lap and checkpoint tracking", "Ordered checkpoints, lap counting, wrong-way "
                                            "detection and race finish."),
            ("Race state and results", "Countdown, race in progress, finish, results and restart."),
        ],
        "optional": ["Weather and time of day", "Garage customisation", "Replay system",
                     "Ranked matchmaking", "Damage model", "Split-screen"],
        "tests": ["Drive the car with each input and confirm acceleration, braking and steering",
                  "Drive into a barrier and confirm the car cannot pass through it",
                  "Complete one full lap and confirm the lap counter and results screen"],
    },
    "adventure": {
        "systems": [
            ("Player traversal", "Walk, run, jump and interact with a grounded character "
                                 "controller."),
            ("Interaction system", "Context prompts and interactable objects that change "
                                   "gameplay state."),
            ("Collectibles and objectives", "Tracked pickups and objective state that persist."),
            ("NPC and dialogue", "At least one NPC with a repeatable interaction and dialogue."),
            ("Save and progression", "Persist position, collectibles and objectives across "
                                     "sessions."),
        ],
        "optional": ["Quest log", "Crafting", "Fast travel", "Photo mode", "Achievements"],
        "tests": ["Walk to an objective, interact with it and confirm progress updates",
                  "Save, restart and confirm collectibles and objectives are restored"],
    },
    "platformer": {
        "systems": [
            ("Character movement", "Run, accelerate and decelerate with tuned gravity."),
            ("Jump and ground detection", "Coyote time, jump buffer and grounded checks."),
            ("Collision", "Solid platforms, slopes and one-way platforms."),
            ("Checkpoints and respawn", "Respawn at the last checkpoint after falling."),
            ("Level progression", "Goal condition that advances to the next level."),
        ],
        "optional": ["Double jump", "Wall jump", "Time trial", "Secret areas"],
        "tests": ["Run, jump and land on every platform type without falling through",
                  "Die and confirm respawn at the last checkpoint",
                  "Reach the level goal and confirm the next level loads"],
    },
    "shooter": {
        "systems": [
            ("Aiming and shooting", "Raycast or projectile firing with fire rate and spread."),
            ("Weapon and ammo", "Weapon state, reload and ammo economy."),
            ("Health and damage", "Damage application, death and respawn."),
            ("Enemy AI", "Detection, pursuit, attack and cover behaviour."),
            ("HUD", "Crosshair, health, ammo and hit feedback."),
        ],
        "optional": ["Weapon attachments", "Skill tree", "Wave mode", "Multiplayer"],
        "tests": ["Fire at a target and confirm hit detection and ammo decrease",
                  "Take damage until death and confirm the death/respawn flow",
                  "Confirm an enemy detects, chases and attacks the player"],
    },
    "rpg": {
        "systems": [
            ("Stats and progression", "Attributes, experience and level-up rules."),
            ("Inventory and equipment", "Items, stacks, equip/unequip and stat effects."),
            ("Quests", "Quest state machine with objectives and rewards."),
            ("Dialogue", "Branching or linear dialogue with safe state changes."),
            ("Save system", "Persist stats, inventory, quests and world state."),
        ],
        "optional": ["Crafting", "Companions", "Faction reputation", "Mounts"],
        "tests": ["Gain experience and confirm level-up changes stats",
                  "Equip an item and confirm the stat change and persistence"],
    },
    "puzzle": {
        "systems": [
            ("Puzzle rules", "Deterministic rule set with a solvable state check."),
            ("Level progression", "Ordered puzzles with completion state."),
            ("Hint and reset", "Player can reset and request a hint without breaking state."),
        ],
        "optional": ["Daily puzzle", "Leaderboard", "Level editor"],
        "tests": ["Solve one puzzle and confirm completion advances the level",
                  "Reset a puzzle and confirm the initial state is restored"],
    },
    "horror": {
        "systems": [
            ("Atmosphere and lighting", "Low-key lighting, fog and audio ambience."),
            ("Threat AI", "Enemy that patrols, detects and chases the player."),
            ("Sanity or survival resource", "A resource that changes under threat."),
            ("Audio cues", "Positional audio for threats and interactions."),
        ],
        "optional": ["Photo mode", "Multiple endings", "Randomised scares"],
        "tests": ["Confirm the threat detects and chases the player",
                  "Confirm the survival resource changes under threat"],
    },
    "survival": {
        "systems": [
            ("Resource gathering", "Gatherable resources with respawn or limits."),
            ("Needs", "Hunger/thirst or equivalent decay and restoration."),
            ("Crafting", "Recipes, requirements and crafted output."),
            ("Day/night and threats", "Time cycle with changing threat behaviour."),
            ("Save system", "Persist world, inventory and needs."),
        ],
        "optional": ["Base building", "Farming", "Trading", "Multiplayer"],
        "tests": ["Gather a resource and craft one recipe",
                  "Let a need decay and restore it, then save and reload"],
    },
    "fighting": {
        "systems": [
            ("Combat states", "Idle, attack, block, hit-stun and KO state machine."),
            ("Hitboxes and hurtboxes", "Per-attack hit detection and per-state hurt areas."),
            ("Damage and balance", "Damage, knockback and balancing data per move."),
            ("Combo and blocking", "Input buffering, combo windows and block rules."),
        ],
        "optional": ["Training mode", "Story mode", "Online rollback", "Character select"],
        "tests": ["Land a hit and confirm damage, hit-stun and knockback",
                  "Block an attack and confirm chip/no damage as designed"],
    },
    "strategy": {
        "systems": [
            ("Selection and commands", "Select units and issue move/attack orders."),
            ("Pathfinding", "Navigation grid or navmesh with obstacle avoidance."),
            ("Economy", "Resource gathering, costs and production."),
            ("AI opponent", "Build order and attack behaviour."),
        ],
        "optional": ["Fog of war", "Tech tree", "Multiplayer", "Campaign"],
        "tests": ["Select a unit, move it and confirm it avoids obstacles",
                  "Produce a unit and confirm the resource cost is applied"],
    },
    "sports": {
        "systems": [
            ("Match rules", "Scoring, timer, fouls and match end."),
            ("Ball/object physics", "Deterministic ball or puck behaviour."),
            ("Team AI", "Positioning and simple team tactics."),
        ],
        "optional": ["Tournament mode", "Career mode", "Local multiplayer"],
        "tests": ["Score a point and confirm the score and match state update"],
    },
    "tower-defense": {
        "systems": [
            ("Enemy waves", "Spawn schedule with increasing difficulty."),
            ("Tower placement", "Grid/valid placement and cost."),
            ("Targeting and combat", "Range, fire rate and target priority."),
            ("Economy and lives", "Currency, rewards and lose condition."),
        ],
        "optional": ["Upgrade tree", "Endless mode", "Boss waves"],
        "tests": ["Place a tower and confirm it damages an enemy in range",
                  "Let an enemy reach the goal and confirm lives decrease"],
    },
    "open-world": {
        "systems": [
            ("World streaming", "Chunk/cell streaming or a bounded world with LOD."),
            ("Navigation and landmarks", "Traversable routes and discoverable landmarks."),
            ("Dynamic activities", "Repeatable activities with rewards."),
            ("Save and progression", "Persist world state and player progression."),
        ],
        "optional": ["Fast travel", "Dynamic weather", "Factions", "Mounts"],
        "tests": ["Travel between two distant areas and confirm streaming/LOD behaves",
                  "Complete one activity and confirm the reward persists after reload"],
    },
}

DEFAULT_GENRE_SYSTEMS = [
    ("Player controller", "Engine-native character/vehicle controller with tuned movement."),
    ("Camera", "Third-person or genre-appropriate camera with collision handling."),
    ("Input", "Remappable input actions for the target platform."),
    ("UI/HUD", "Core gameplay state visible to the player."),
    ("Audio", "Music and gameplay feedback."),
    ("Save/settings", "Persist settings and core progress where the genre needs it."),
]

ANIMATION_BY_MECHANIC = {
    "jumping": ["idle", "walk/run", "jump start", "jump loop", "land"],
    "climbing": ["climb up", "climb down", "climb idle", "ledge grab"],
    "swimming": ["swim idle", "swim forward", "dive", "surface"],
    "driving": ["vehicle idle", "accelerate", "brake", "steer left", "steer right"],
    "drifting": ["drift start", "drift loop", "drift exit"],
    "shooting": ["aim", "fire", "reload", "hit reaction", "death"],
    "combat": ["attack 1", "attack 2", "block", "hit reaction", "death"],
    "enemies": ["idle", "walk", "chase", "attack", "death"],
    "collectibles": ["pickup"],
    "multiplayer": ["emote/gesture set (optional)"],
}

RIG_BY_CHARACTER = {
    "monkey": {
        "rig": "quadruped-capable / non-humanoid rig",
        "animations": ["idle", "walk", "run", "jump", "climb", "land"],
        "warning": "Do not retarget humanoid locomotion clips blindly onto a monkey; "
                   "verify spine chain, limb proportions and rest pose.",
    },
    "human": {"rig": "humanoid rig (Unity Humanoid / UE mannequin compatible)",
              "animations": ["idle", "walk", "run", "jump", "land"], "warning": None},
    "robot": {"rig": "mechanical/humanoid rig with rigid parts",
              "animations": ["idle", "walk", "run", "attack"], "warning": None},
    "dragon": {"rig": "winged quadruped rig", "animations": ["idle", "walk", "fly", "attack"],
               "warning": "Wing and tail chains usually need custom clips."},
    "knight": {"rig": "humanoid rig", "animations": ["idle", "walk", "attack", "block", "death"],
               "warning": None},
    "soldier": {"rig": "humanoid rig", "animations": ["idle", "walk", "aim", "fire", "death"],
                "warning": None},
    "zombie": {"rig": "humanoid rig", "animations": ["idle", "shamble", "attack", "death"],
               "warning": None},
    "animal": {"rig": "species-appropriate quadruped rig",
               "animations": ["idle", "walk", "run", "jump"],
               "warning": "Choose clips authored for the same body plan."},
    "car": {"rig": "vehicle rig (no skeleton required)",
            "animations": ["wheel spin", "suspension travel", "steering"],
            "warning": "Vehicles use wheel colliders/animations, not humanoid clips."},
    "ship": {"rig": "vehicle/mechanical rig", "animations": ["engine idle", "thruster"],
             "warning": None},
}

PERFORMANCE_TARGETS = {
    "pc": {"fps": "60 fps at 1080p on the reference machine",
           "budget": "Keep draw calls below ~2,000 and total scene triangles below ~2M."},
    "mobile": {"fps": "30-60 fps on the target phone",
               "budget": "Prefer <100k triangles per character, <500 draw calls, baked lighting."},
    "console": {"fps": "60 fps target with a 30 fps fallback",
                "budget": "Profile on devkit; keep within platform memory limits."},
    "web": {"fps": "60 fps on a mid-range laptop",
            "budget": "Keep the initial download small; compress textures and use LODs."},
    "vr": {"fps": "72-90 fps sustained",
           "budget": "Single-pass stereo where possible; avoid full-screen post effects."},
}

DEFAULT_ASSUMPTIONS = {
    "engine": "Unity for 3D, Godot for a small 2D prototype when no engine is requested",
    "platform": "PC (Windows) for development, with a later mobile/web port decision",
    "scope": "one vertical slice first, not the full content plan",
    "art": "stylised-realistic placeholder art that can be replaced without rework",
    "character": "Blender-authored or licensed asset; Meshy optional and credit-gated",
    "environment": "Blender blockout plus engine terrain, replaced by production art later",
}


@dataclass
class Match:
    category: str
    canonical: str
    phrase: str
    start: int
    end: int


@dataclass
class ConceptSet:
    values: dict[str, list[str]] = field(default_factory=dict)
    matches: list[Match] = field(default_factory=list)

    def add(self, category: str, canonical: str) -> None:
        bucket = self.values.setdefault(category, [])
        if canonical not in bucket:
            bucket.append(canonical)

    def get(self, category: str) -> list[str]:
        return self.values.get(category, [])


def _compile_index() -> list[tuple[str, str, str, re.Pattern]]:
    index: list[tuple[str, str, str, re.Pattern]] = []
    for category, entries in LEXICON.items():
        for canonical, phrases in entries.items():
            for phrase in phrases:
                cleaned = phrase.strip()
                if not cleaned:
                    continue
                parts = [re.escape(part) for part in cleaned.split()]
                pattern = re.compile(r"(?<!\w)" + r"\s+".join(parts) + r"(?!\w)",
                                     re.IGNORECASE | re.UNICODE)
                index.append((cleaned.lower(), category, canonical, pattern))
    # longest surface form first so "racing game" beats "race"
    index.sort(key=lambda item: len(item[0]), reverse=True)
    return index


_INDEX = _compile_index()


def _surface_terms() -> set[str]:
    return {phrase for phrase, _, _, _ in _INDEX}


SURFACE_TERMS = _surface_terms()


def match_concepts(text: str) -> tuple[ConceptSet, list[dict]]:
    """Return matched concepts plus a traceable list of matches."""
    concepts = ConceptSet()
    raw: list[Match] = []
    for phrase, category, canonical, pattern in _INDEX:
        for found in pattern.finditer(text):
            raw.append(Match(category, canonical, found.group(0), found.start(), found.end()))
    # Prefer the longest match at each span; allow the same phrase to satisfy
    # different categories (e.g. "race" as genre and as a track).
    raw.sort(key=lambda m: (m.start, -(m.end - m.start)))
    seen: set[tuple[int, int, str, str]] = set()
    for match in raw:
        key = (match.start, match.end, match.category, match.canonical)
        if key in seen:
            continue
        seen.add(key)
        concepts.add(match.category, match.canonical)
        concepts.matches.append(match)
    trace = [{
        "category": m.category,
        "value": m.canonical,
        "matched_text": m.phrase,
        "start": m.start,
        "end": m.end,
    } for m in sorted(concepts.matches, key=lambda m: (m.start, m.end))]
    return concepts, trace


def detect_languages(text: str) -> dict:
    lowered = text.lower()
    urdu_chars = len(re.findall(r"[\u0600-\u06FF]", text))
    roman = sorted({hint for hint in ROMAN_URDU_HINTS
                    if re.search(r"(?<!\w)" + re.escape(hint) + r"(?!\w)", lowered)})
    urdu_terms = sorted({hint for hint in URDU_HINTS if hint in text})
    languages = []
    if re.search(r"[A-Za-z]", text):
        languages.append("english")
    if roman:
        languages.append("roman-urdu")
    if urdu_chars:
        languages.append("urdu")
    return {
        "detected": languages or ["unknown"],
        "mixed": len(languages) > 1,
        "roman_urdu_terms": roman,
        "urdu_terms": urdu_terms,
        "urdu_character_count": urdu_chars,
    }


def _negative_context(text: str, match: Match, window: int = 28) -> bool:
    prefix = text[max(0, match.start - window):match.start].lower()
    # Postpositions are only meaningful directly after the noun ("bandooq nahi
    # chahiye"), so the suffix window stays short to avoid negating a different
    # clause.
    suffix = text[match.end:match.end + 16].lower()
    return (any(marker in prefix for marker in NEGATION_MARKERS)
            or any(marker in suffix for marker in NEGATION_SUFFIX))


def extract_exclusions(text: str) -> list[dict]:
    """Find concepts the user explicitly rejected.

    Negative markers are checked in the short window before a matched phrase,
    which handles "no guns", "without multiplayer" and "multiplayer ke baghair".
    """
    _, trace = match_concepts(text)
    exclusions = []
    for item in trace:
        if item["category"] in ("engine", "dimension", "genre"):
            continue
        concept = Match(item["category"], item["value"], item["matched_text"],
                        item["start"], item["end"])
        if _negative_context(text, concept):
            exclusions.append({
                "category": item["category"],
                "value": item["value"],
                "matched_text": item["matched_text"],
                "reason": "negated in the original request",
            })
    # Deduplicate by category+value.
    unique: dict[tuple[str, str], dict] = {}
    for item in exclusions:
        unique[(item["category"], item["value"])] = item
    return list(unique.values())


def positive_values(text: str) -> dict[str, list[str]]:
    """Concepts mentioned outside a negation window.

    Used only for conflict detection, so an explicit "no guns" is not mistaken
    for a request for guns.
    """
    _, trace = match_concepts(text)
    values: dict[str, list[str]] = {}
    for item in trace:
        match = Match(item["category"], item["value"], item["matched_text"],
                      item["start"], item["end"])
        if _negative_context(text, match):
            continue
        bucket = values.setdefault(item["category"], [])
        if item["value"] not in bucket:
            bucket.append(item["value"])
    return values


def extract_constraints(text: str) -> list[dict]:
    constraints = []
    pattern = re.compile(
        r"(?<!\w)(\d{1,3})\s*(levels?|tracks?|players?|characters?|enemies?|maps?|"
        r"missions?|hours?|minutes?)(?!\w)", re.IGNORECASE)
    for found in pattern.finditer(text):
        constraints.append({
            "value": int(found.group(1)),
            "unit": found.group(2).lower().rstrip("s"),
            "matched_text": found.group(0),
        })
    return constraints


def _objective(concepts: ConceptSet) -> str:
    dims = concepts.get("dimension")
    genres = concepts.get("genre")
    chars = concepts.get("character")
    envs = concepts.get("environment")
    style = concepts.get("style")
    parts = []
    qualifier = ""
    if style:
        qualifier = f"{style[0].replace('-', ' ')} "
    dimension = ""
    if "2.5d" in dims:
        dimension = "2.5D "
    elif "2d" in dims and "3d" not in dims:
        dimension = "2D "
    elif "3d" in dims:
        dimension = "3D "
    if genres:
        genre = genres[0].replace("-", " ")
        parts.append(f"Build a {qualifier}{dimension}{genre} game")
    elif chars or envs:
        parts.append(f"Build a {qualifier}{dimension}game")
    else:
        parts.append("Build a game")
    if chars:
        parts[-1] += f" featuring a {', '.join(chars)}"
    if envs:
        if len(envs) == 1:
            parts[-1] += f" set in a {envs[0]} environment"
        else:
            parts[-1] += " set across " + " and ".join(envs) + " environments"
    return parts[-1] + "."


def _requirement(counter: list[int], category: str, statement: str, *,
                 source: str, classification: str, priority: str,
                 acceptance: str, confidence: str = "high",
                 tasks: list[str] | None = None) -> dict:
    counter[0] += 1
    return {
        "id": f"R-{counter[0]:03d}",
        "category": category,
        "statement": statement,
        "source_text": source,
        "classification": classification,
        "priority": priority,
        "confidence": confidence,
        "acceptance_test": acceptance,
        "implementation_tasks": tasks or [],
        "status": "pending",
    }


def _explicit_requirements(concepts: ConceptSet, text: str,
                           counter: list[int]) -> list[dict]:
    requirements = []
    by_category = {
        "dimension": ("Dimension", "P0",
                      "The game renders and plays in the requested perspective."),
        "genre": ("Genre", "P0", "The core loop matches the requested genre."),
        "engine": ("Engine", "P0", "The project builds with the requested engine."),
        "platform": ("Platform", "P0", "The game runs on the requested target platform."),
        "style": ("Art direction", "P1", "Delivered assets follow the requested style."),
        "character": ("Character", "P1", "The requested character exists and is controllable."),
        "environment": ("Environment", "P1", "The requested environment exists and is traversable."),
        "mechanic": ("Gameplay", "P0", "The requested mechanic is implemented and playable."),
    }
    for category, values in concepts.values.items():
        if category not in by_category:
            continue
        label, priority, acceptance = by_category[category]
        for value in values:
            # Use the first matched phrase for traceability.
            match = next((m for m in concepts.matches
                          if m.category == category and m.canonical == value), None)
            source = match.phrase if match else value
            requirements.append(_requirement(
                counter, category, f"{label}: {value.replace('-', ' ')}",
                source=source, classification="explicit", priority=priority,
                acceptance=acceptance,
            ))
    return requirements


def _template_systems(concepts: ConceptSet) -> list[tuple[str, str]]:
    systems: list[tuple[str, str]] = []
    for genre in concepts.get("genre"):
        template = GENRE_TEMPLATES.get(genre)
        if template:
            systems.extend(template["systems"])
    if not systems:
        systems.extend(DEFAULT_GENRE_SYSTEMS)
    else:
        seen = {name for name, _ in systems}
        for name, detail in DEFAULT_GENRE_SYSTEMS:
            if name not in seen and name in ("Player controller", "Camera", "UI/HUD"):
                systems.append((name, detail))
    # Mechanic-specific systems.
    mechanics = set(concepts.get("mechanic"))
    extra = {
        "multiplayer": ("Networking", "Authoritative state sync, spawn, join/leave and latency "
                                       "handling; online vs local must be decided."),
        "inventory": ("Inventory model", "Item definitions, stacking and persistence."),
        "crafting": ("Crafting model", "Recipes, resource costs and output."),
        "quests": ("Quest state", "Objectives, completion and rewards."),
        "stealth": ("Detection model", "Vision/hearing detection, suspicion and alert states."),
        "procedural": ("Procedural generation", "Seeded generator with validation of generated "
                                                 "layout."),
        "save-system": ("Save/load", "Versioned serialisation with a round-trip test."),
    }
    for mechanic, system in extra.items():
        if mechanic in mechanics:
            systems.append(system)
    deduped = []
    seen = set()
    for name, detail in systems:
        if name not in seen:
            seen.add(name)
            deduped.append((name, detail))
    return deduped


def _implied_requirements(concepts: ConceptSet, counter: list[int]) -> list[dict]:
    requirements = []
    for name, detail in _template_systems(concepts):
        requirements.append(_requirement(
            counter, "system", name,
            source="implied by genre/mechanics", classification="implied",
            priority="P1", acceptance=f"{name} works in a playable build: {detail}",
            confidence="medium", tasks=[detail],
        ))
    return requirements


def _technical_requirements(concepts: ConceptSet, counter: list[int]) -> list[dict]:
    requirements = []
    dims = set(concepts.get("dimension"))
    engines = concepts.get("engine")
    mechanics = set(concepts.get("mechanic"))
    if "3d" in dims or "2.5d" in dims:
        requirements.append(_requirement(
            counter, "technical", "3D asset import pipeline",
            source="implied by 3D/2.5D dimension", classification="technical",
            priority="P0", confidence="high",
            acceptance="A test model imports with correct scale, materials and colliders.",
        ))
    if "2d" in dims:
        requirements.append(_requirement(
            counter, "technical", "2D sprite and tile pipeline",
            source="implied by 2D dimension", classification="technical",
            priority="P0", confidence="high",
            acceptance="A test sprite and tilemap import with correct pixels-per-unit.",
        ))
    for engine in engines:
        requirements.append(_requirement(
            counter, "technical", f"{engine.title()} project configuration",
            source=f"requested engine: {engine}", classification="technical",
            priority="P0", confidence="high",
            acceptance=f"The {engine} project opens, compiles and produces a build.",
        ))
    if "multiplayer" in mechanics:
        requirements.append(_requirement(
            counter, "technical", "Multiplayer transport and authority model",
            source="implied by multiplayer", classification="technical",
            priority="P0", confidence="medium",
            acceptance="Two clients connect, see shared state and survive a disconnect.",
        ))
    requirements.append(_requirement(
        counter, "technical", "Version control and reproducible project setup",
        source="studio baseline", classification="technical", priority="P1",
        confidence="high",
        acceptance="A clean clone/checkout opens and builds using documented steps.",
    ))
    return requirements


def _optional_requirements(concepts: ConceptSet, counter: list[int],
                           exclusions: list[dict] | None = None) -> list[dict]:
    requirements = []
    optional: list[str] = []
    for genre in concepts.get("genre"):
        optional.extend(GENRE_TEMPLATES.get(genre, {}).get("optional", []))
    if not optional:
        optional = ["Photo mode", "Achievements", "Accessibility options"]
    excluded_values = {str(item.get("value", "")).lower() for item in (exclusions or [])}
    for idea in optional:
        # A suggestion must not reintroduce a concept the user explicitly excluded.
        if any(value and value in idea.lower() for value in excluded_values):
            continue
        requirements.append(_requirement(
            counter, "optional", idea,
            source="AI recommendation, not requested", classification="optional",
            priority="P3", confidence="low",
            acceptance=f"If built, {idea} works without breaking the core loop.",
        ))
    return requirements


def _unresolved(concepts: ConceptSet, installed_engines: list[str] | None,
                known_engine: str | None) -> tuple[list[dict], list[dict]]:
    unresolved: list[dict] = []
    questions: list[dict] = []
    dims = concepts.get("dimension")
    genres = concepts.get("genre")
    engines = concepts.get("engine")
    platforms = concepts.get("platform")

    if not engines:
        options = installed_engines or []
        recommended = None
        if "2d" in dims and "3d" not in dims:
            recommended = "godot" if "godot" in options or not options else options[0]
        else:
            recommended = "unity" if "unity" in options or not options else options[0]
        unresolved.append({
            "topic": "engine", "material": True,
            "reason": "The engine determines project structure, scripting, asset import and "
                      "build pipeline.",
            "recommended": recommended or known_engine or "unity",
            "default_used": None,
            "installed_options": options,
        })
        questions.append({
            "question": "Which engine should this be built in?",
            "why": "It changes every downstream implementation step.",
            "options": options or ["Unity", "Unreal Engine", "Godot"],
            "recommended": recommended or "unity",
        })
    if not platforms:
        unresolved.append({
            "topic": "platform", "material": True,
            "reason": "Performance budgets, input and build targets depend on it.",
            "recommended": "pc", "default_used": "pc",
        })
        questions.append({
            "question": "Which platform is the first target?",
            "why": "Input, performance budgets and build settings differ.",
            "options": ["PC (Windows)", "Mobile", "Web", "Console"],
            "recommended": "PC (Windows)",
        })
    if "multiplayer" in concepts.get("mechanic"):
        unresolved.append({
            "topic": "multiplayer-mode", "material": True,
            "reason": "Online vs local changes networking, testing and cost.",
            "recommended": "local co-op first, online later",
            "default_used": None,
        })
        questions.append({
            "question": "Should multiplayer be online or local, and for how many players?",
            "why": "It determines the networking architecture and test plan.",
            "options": ["Local co-op (2-4)", "Online (2-8)", "Online (large scale)"],
            "recommended": "Local co-op first",
        })
    if not concepts.get("style"):
        unresolved.append({
            "topic": "art-style", "material": True,
            "reason": "Asset sources, polygon budgets and shaders depend on style.",
            "recommended": "stylised-realistic", "default_used": "stylised-realistic",
        })
        questions.append({
            "question": "What visual style should the game use?",
            "why": "It determines asset sources and quality bars.",
            "options": ["Realistic", "Stylised", "Low-poly", "Pixel art"],
            "recommended": "Stylised",
        })
    if concepts.get("character") and not any(
            m in concepts.get("mechanic") for m in ("inventory",)):
        unresolved.append({
            "topic": "character-source", "material": False,
            "reason": "Character creation method affects time, cost and licensing.",
            "recommended": "Blender-authored or licensed base mesh; Meshy optional",
            "default_used": "Blender/licensed",
        })
    if not dims:
        unresolved.append({
            "topic": "dimension", "material": True,
            "reason": "2D and 3D have different physics, assets, cameras and controls.",
            "recommended": "3D" if not genres or "puzzle" not in genres else "2D",
            "default_used": None,
        })
        questions.append({
            "question": "Should the game be 2D or 3D?",
            "why": "It changes the entire asset and gameplay pipeline.",
            "options": ["3D", "2D", "2.5D"],
            "recommended": "3D",
        })
    scope_default = "one vertical slice"
    unresolved.append({
        "topic": "scope", "material": False,
        "reason": "Prevents promising a full content plan before the core loop works.",
        "recommended": scope_default, "default_used": scope_default,
    })
    return unresolved, questions[:5]


def _conflicts(concepts: ConceptSet, exclusions: list[dict],
               positive: dict[str, list[str]]) -> list[dict]:
    conflicts = []
    dims = concepts.get("dimension")
    engines = concepts.get("engine")
    styles = concepts.get("style")
    if len(dims) > 1:
        if not (set(dims) <= {"2.5d"} or set(dims) == {"2d", "3d", "2.5d"}):
            conflicts.append({
                "type": "contradictory_dimension",
                "detail": f"Multiple dimensions requested: {dims}",
                "resolution": "Choose one primary rendering dimension; 2.5D is the only "
                              "combination that is unambiguous.",
            })
    if len(engines) > 1:
        conflicts.append({
            "type": "multiple_engines",
            "detail": f"Multiple engines requested: {engines}",
            "resolution": "Pick one engine for the project; assets can be shared but the "
                          "project cannot live in two engines.",
        })
    if "realistic" in styles and ({"cartoon", "pixel-art", "anime", "low-poly"} & set(styles)):
        conflicts.append({
            "type": "art_style_conflict",
            "detail": f"Realistic was requested together with {styles}",
            "resolution": "Decide whether 'realistic' means lighting/materials or photo-real "
                          "assets; otherwise the art direction will be incoherent.",
        })
    for exclusion in exclusions:
        if exclusion["value"] in positive.get(exclusion["category"], []):
            conflicts.append({
                "type": "requested_and_excluded",
                "detail": f"{exclusion['value']} appears to be both requested and excluded "
                          f"('{exclusion['matched_text']}')",
                "resolution": "Confirm the intended behaviour with the user before implementation.",
            })
    return conflicts


def analyze_request(text: str, *, installed_engines: list[str] | None = None,
                   known_engine: str | None = None,
                   known_platform: str | None = None) -> dict:
    """Turn a free-form request into a traceable, classified requirement set."""
    original = (text or "").strip()
    if not original:
        raise ValueError("request text is required")
    if len(original) > 20_000:
        raise ValueError("request text is too long (max 20000 characters)")

    concepts, trace = match_concepts(original)
    exclusions = extract_exclusions(original)
    constraints = extract_constraints(original)
    positive_snapshot = positive_values(original)

    # Remove excluded concepts from the positive set so they never become an
    # explicit requirement by accident.
    for exclusion in exclusions:
        bucket = concepts.values.get(exclusion["category"])
        if bucket and exclusion["value"] in bucket:
            bucket.remove(exclusion["value"])
            concepts.values[exclusion["category"]] = bucket

    languages = detect_languages(original)
    counter = [0]
    explicit = _explicit_requirements(concepts, original, counter)
    implied = _implied_requirements(concepts, counter)
    technical = _technical_requirements(concepts, counter)
    optional = _optional_requirements(concepts, counter, exclusions)
    unresolved, questions = _unresolved(concepts, installed_engines, known_engine)
    conflicts = _conflicts(concepts, exclusions, positive_snapshot)

    if known_platform and not concepts.get("platform"):
        concepts.add("platform", known_platform)

    all_requirements = explicit + implied + technical + optional
    confidence = "high" if explicit else "low"
    if languages["mixed"]:
        confidence = "medium" if explicit else "low"

    recommendations = []
    if not concepts.get("engine"):
        recommendations.append(
            "Choose the engine from detected installations before planning asset work.")
    if "multiplayer" in concepts.get("mechanic"):
        recommendations.append("Build the single-player loop before networking.")
    if "realistic" in concepts.get("style") and "mobile" in concepts.get("platform"):
        recommendations.append("Realistic art on mobile needs aggressive LODs and baked "
                              "lighting; validate the performance budget early.")
    if concepts.get("character") and concepts.get("character")[0] != "human":
        recommendations.append(
            "Use a species-appropriate rig; do not assume humanoid retargeting will work.")

    summary = _objective(concepts)
    return {
        "ok": True,
        "original_request": original,
        "language": languages,
        "summary": summary,
        "understanding": {
            "objective": summary,
            "game_genre": concepts.get("genre"),
            "dimension": concepts.get("dimension"),
            "engine_requested": concepts.get("engine"),
            "target_platform": concepts.get("platform"),
            "characters": concepts.get("character"),
            "environment": concepts.get("environment"),
            "visual_style": concepts.get("style"),
            "mechanics": concepts.get("mechanic"),
        },
        "matched_terms": trace,
        "constraints": constraints,
        "exclusions": exclusions,
        "conflicts": conflicts,
        "requirements": {
            "explicit": explicit,
            "implied": implied,
            "technical_dependencies": technical,
            "optional_enhancements": optional,
        },
        "unresolved": unresolved,
        "questions": questions,
        "recommendations": recommendations,
        "assumptions_available": DEFAULT_ASSUMPTIONS,
        "counts": {
            "explicit": len(explicit),
            "implied": len(implied),
            "technical": len(technical),
            "optional": len(optional),
            "unresolved": len(unresolved),
            "all": len(all_requirements),
        },
        "confidence": confidence,
        "notes": [
            "Explicit requirements come from the user's words. Implied, technical and "
            "optional items are engineering recommendations, not user demands.",
            "A matched term is evidence of intent, not proof of a complete specification.",
        ],
        "_concepts": concepts.values,
        "_matched": [(m.category, m.canonical) for m in concepts.matches],
    }
