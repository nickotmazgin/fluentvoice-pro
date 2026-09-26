"""Single source of truth for FluentVoice Pro's neural voices.

Settings (voice list + Preferred Voices), the tray menu, auto-routing and the voice test
all read from here, so they can no longer drift apart. Every id was checked against
Microsoft Edge's live voice list (edge_tts.list_voices()); tests/test_voices.py guards
the structure.
"""

from __future__ import annotations

# family key → display name. Keys are also the preferred_voices / auto-route keys
# ("cjk" is Japanese and "cyrillic" is Russian, kept for existing config files).
LANGUAGES = {
    "english": "English",
    "hebrew": "Hebrew",
    "arabic": "Arabic",
    "spanish": "Spanish",
    "french": "French",
    "german": "German",
    "italian": "Italian",
    "portuguese": "Portuguese",
    "cyrillic": "Russian",
    "cjk": "Japanese",
    "chinese": "Chinese",
    "korean": "Korean",
}

# Languages written in Latin script: "Multilingual" voices read these natively,
# so auto-routing leaves them alone.
LATIN_FAMILIES = {"english", "spanish", "french", "german", "italian", "portuguese"}

# (voice id, Settings / tray label, family)
CATALOG = [
    # English — US
    ("en-US-AndrewMultilingualNeural", "Andrew Multilingual (US HD Male)", "english"),
    ("en-US-AvaMultilingualNeural", "Ava Multilingual (US HD Female)", "english"),
    ("en-US-BrianMultilingualNeural", "Brian Multilingual (US HD Male, Casual)", "english"),
    ("en-US-EmmaMultilingualNeural", "Emma Multilingual (US HD Female, Expressive)", "english"),
    ("en-US-ChristopherNeural", "Christopher (US HD Male, Narration)", "english"),
    ("en-US-EricNeural", "Eric (US HD Male)", "english"),
    ("en-US-GuyNeural", "Guy (US HD Male, Studio)", "english"),
    ("en-US-JennyNeural", "Jenny (US HD Female, Studio)", "english"),
    ("en-US-AriaNeural", "Aria (US HD Female, Friendly)", "english"),
    ("en-US-MichelleNeural", "Michelle (US HD Female)", "english"),
    # English — UK, Australia, Canada, Ireland, India
    ("en-GB-RyanNeural", "Ryan (UK HD Male)", "english"),
    ("en-GB-ThomasNeural", "Thomas (UK HD Male)", "english"),
    ("en-GB-SoniaNeural", "Sonia (UK HD Female)", "english"),
    ("en-GB-LibbyNeural", "Libby (UK HD Female)", "english"),
    ("en-AU-WilliamMultilingualNeural", "William Multilingual (Australia HD Male)", "english"),
    ("en-AU-NatashaNeural", "Natasha (Australia HD Female)", "english"),
    ("en-CA-LiamNeural", "Liam (Canada HD Male)", "english"),
    ("en-CA-ClaraNeural", "Clara (Canada HD Female)", "english"),
    ("en-IE-ConnorNeural", "Connor (Ireland HD Male)", "english"),
    ("en-IE-EmilyNeural", "Emily (Ireland HD Female)", "english"),
    ("en-IN-PrabhatNeural", "Prabhat (India HD Male)", "english"),
    ("en-IN-NeerjaNeural", "Neerja (India HD Female)", "english"),
    # Hebrew
    ("he-IL-AvriNeural", "Avri (Hebrew HD Male)", "hebrew"),
    ("he-IL-HilaNeural", "Hila (Hebrew HD Female)", "hebrew"),
    # Arabic
    ("ar-SA-HamedNeural", "Hamed (Arabic HD Male, Saudi Arabia)", "arabic"),
    ("ar-SA-ZariyahNeural", "Zariyah (Arabic HD Female, Saudi Arabia)", "arabic"),
    ("ar-EG-ShakirNeural", "Shakir (Arabic HD Male, Egypt)", "arabic"),
    ("ar-EG-SalmaNeural", "Salma (Arabic HD Female, Egypt)", "arabic"),
    # Spanish
    ("es-ES-AlvaroNeural", "Alvaro (Spanish HD Male, Spain)", "spanish"),
    ("es-ES-ElviraNeural", "Elvira (Spanish HD Female, Spain)", "spanish"),
    ("es-MX-JorgeNeural", "Jorge (Spanish HD Male, Mexico)", "spanish"),
    ("es-MX-DaliaNeural", "Dalia (Spanish HD Female, Mexico)", "spanish"),
    # French
    ("fr-FR-HenriNeural", "Henri (French HD Male, France)", "french"),
    ("fr-FR-DeniseNeural", "Denise (French HD Female, France)", "french"),
    ("fr-FR-RemyMultilingualNeural", "Remy Multilingual (French HD Male)", "french"),
    ("fr-FR-VivienneMultilingualNeural", "Vivienne Multilingual (French HD Female)", "french"),
    ("fr-CA-AntoineNeural", "Antoine (French HD Male, Canada)", "french"),
    ("fr-CA-SylvieNeural", "Sylvie (French HD Female, Canada)", "french"),
    # German
    ("de-DE-ConradNeural", "Conrad (German HD Male)", "german"),
    ("de-DE-KatjaNeural", "Katja (German HD Female)", "german"),
    ("de-DE-FlorianMultilingualNeural", "Florian Multilingual (German HD Male)", "german"),
    ("de-DE-SeraphinaMultilingualNeural", "Seraphina Multilingual (German HD Female)", "german"),
    # Italian
    ("it-IT-DiegoNeural", "Diego (Italian HD Male)", "italian"),
    ("it-IT-ElsaNeural", "Elsa (Italian HD Female)", "italian"),
    ("it-IT-GiuseppeMultilingualNeural", "Giuseppe Multilingual (Italian HD Male)", "italian"),
    ("it-IT-IsabellaNeural", "Isabella (Italian HD Female)", "italian"),
    # Portuguese
    ("pt-BR-AntonioNeural", "Antonio (Portuguese HD Male, Brazil)", "portuguese"),
    ("pt-BR-FranciscaNeural", "Francisca (Portuguese HD Female, Brazil)", "portuguese"),
    ("pt-BR-ThalitaMultilingualNeural", "Thalita Multilingual (Portuguese HD Female, Brazil)", "portuguese"),
    ("pt-PT-DuarteNeural", "Duarte (Portuguese HD Male, Portugal)", "portuguese"),
    ("pt-PT-RaquelNeural", "Raquel (Portuguese HD Female, Portugal)", "portuguese"),
    # Russian
    ("ru-RU-DmitryNeural", "Dmitry (Russian HD Male)", "cyrillic"),
    ("ru-RU-SvetlanaNeural", "Svetlana (Russian HD Female)", "cyrillic"),
    # Japanese, Chinese, Korean
    ("ja-JP-KeitaNeural", "Keita (Japanese HD Male)", "cjk"),
    ("ja-JP-NanamiNeural", "Nanami (Japanese HD Female)", "cjk"),
    ("zh-CN-YunxiNeural", "Yunxi (Chinese HD Male)", "chinese"),
    ("zh-CN-XiaoxiaoNeural", "Xiaoxiao (Chinese HD Female)", "chinese"),
    ("ko-KR-InJoonNeural", "InJoon (Korean HD Male)", "korean"),
    ("ko-KR-HyunsuMultilingualNeural", "Hyunsu Multilingual (Korean HD Male)", "korean"),
    ("ko-KR-SunHiNeural", "SunHi (Korean HD Female)", "korean"),
]

DEFAULT_VOICE = "en-US-AndrewMultilingualNeural"

DEFAULT_PREFERRED = {
    "english": "en-US-AndrewMultilingualNeural",
    "hebrew": "he-IL-AvriNeural",
    "arabic": "ar-SA-HamedNeural",
    "spanish": "es-ES-AlvaroNeural",
    "french": "fr-FR-HenriNeural",
    "german": "de-DE-ConradNeural",
    "italian": "it-IT-DiegoNeural",
    "portuguese": "pt-BR-AntonioNeural",
    "cyrillic": "ru-RU-DmitryNeural",
    "cjk": "ja-JP-KeitaNeural",
    "chinese": "zh-CN-YunxiNeural",
    "korean": "ko-KR-InJoonNeural",
}

# Voices Microsoft retired → closest current voice (migrates saved settings).
RETIRED = {
    "en-US-DavisNeural": "en-US-ChristopherNeural",
    "en-AU-WilliamNeural": "en-AU-WilliamMultilingualNeural",
}

# Right-to-left languages: Settings right-aligns their text.
RTL_FAMILIES = {"hebrew", "arabic"}

# Default "Preview & Test Voice" sentence per language. Hebrew/Arabic keep their
# punctuation between RTL words and end without a period, so they also display
# correctly in Tk's left-to-right text boxes.
SAMPLE_TEXT = {
    "english": "Welcome to FluentVoice Pro! High-definition natural speech synthesis is active.",
    "hebrew": "ברוכים הבאים! הקול הטבעי של FluentVoice Pro פעיל באיכות גבוהה",
    "arabic": "مرحبًا بك! الصوت الطبيعي من FluentVoice Pro يعمل بجودة عالية",
    "spanish": "¡Bienvenido a FluentVoice Pro! La voz natural en alta definición está activa.",
    "french": "Bienvenue dans FluentVoice Pro ! La voix naturelle haute définition est active.",
    "german": "Willkommen bei FluentVoice Pro! Die natürliche HD-Sprachausgabe ist aktiv.",
    "italian": "Benvenuto in FluentVoice Pro! La voce naturale in alta definizione è attiva.",
    "portuguese": "Bem-vindo ao FluentVoice Pro! A voz natural em alta definição está ativa.",
    "cyrillic": "Добро пожаловать в FluentVoice Pro! Естественный голос высокого качества включён.",
    "cjk": "FluentVoice Pro へようこそ！高品質な自然音声が有効です。",
    "chinese": "欢迎使用 FluentVoice Pro！高清自然语音已启用。",
    "korean": "FluentVoice Pro에 오신 것을 환영합니다! 고품질 자연 음성이 켜져 있습니다.",
}

_BY_ID = {v: (label, fam) for v, label, fam in CATALOG}

_PREFIX_FAMILY = {
    "en-": "english", "he-": "hebrew", "ar-": "arabic", "es-": "spanish", "fr-": "french",
    "de-": "german", "it-": "italian", "pt-": "portuguese", "ru-": "cyrillic", "ja-": "cjk",
    "zh-": "chinese", "ko-": "korean",
}


def current_id(voice: str) -> str:
    """Map a retired voice id to its replacement."""
    return RETIRED.get(voice, voice)


def label_for(voice: str) -> str:
    return _BY_ID.get(current_id(voice), (voice, ""))[0]


def short_name(voice: str) -> str:
    """'Avri (Hebrew HD Male)' → 'Avri'."""
    return label_for(voice).split(" (")[0]


def family_of(voice: str) -> str:
    """Language family of a voice id (neural ids by locale prefix; others → english)."""
    v = current_id(voice or "")
    if v in _BY_ID:
        return _BY_ID[v][1]
    low = v.lower()
    for prefix, fam in _PREFIX_FAMILY.items():
        if low.startswith(prefix):
            return fam
    return "english"


def is_multilingual(voice: str) -> bool:
    return "multilingual" in (voice or "").lower()


def can_read(voice: str, language: str) -> bool:
    """True when this voice reads `language` natively, so auto-routing should keep it."""
    fam = family_of(voice)
    if fam == language:
        return True
    return is_multilingual(voice) and language in LATIN_FAMILIES and fam in LATIN_FAMILIES


def voices_for(family: str) -> list[tuple[str, str]]:
    """[(voice id, label)] for one language, in catalog order."""
    return [(v, label) for v, label, fam in CATALOG if fam == family]


def sample_text(voice: str) -> str:
    return SAMPLE_TEXT.get(family_of(voice), SAMPLE_TEXT["english"])
