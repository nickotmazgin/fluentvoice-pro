"""Single source of truth for FluentVoice Pro's neural voices.

Settings (voice list + Preferred Voices), the tray menu, auto-routing and the voice test
all read from here, so they can no longer drift apart. Every id was checked against
Microsoft Edge's live voice list (edge_tts.list_voices()); tests/test_voices.py guards
the structure.
"""

from __future__ import annotations

import re

from . import local_catalog

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
    "hindi": "Hindi",
    "marathi": "Marathi",
    "bengali": "Bengali",
    "tamil": "Tamil",
    "telugu": "Telugu",
    "gujarati": "Gujarati",
    "kannada": "Kannada",
    "malayalam": "Malayalam",
    "thai": "Thai",
    "icelandic": "Icelandic",
}

# Languages written in Latin script: "Multilingual" voices read these natively,
# so auto-routing leaves them alone.
LATIN_FAMILIES = {"english", "spanish", "french", "german", "italian", "portuguese"}

# Languages that share a script: auto-route can only see the script (Devanagari), so text
# it detects as Hindi is left to a Marathi voice the user picked, and vice versa.
SAME_SCRIPT = {"marathi": "hindi", "hindi": "marathi"}

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
    ("en-AU-WilliamMultilingualNeural", "William Multilingual (Australian English HD Male)", "english"),
    ("en-AU-NatashaNeural", "Natasha (Australian English HD Female)", "english"),
    ("en-CA-LiamNeural", "Liam (Canadian English HD Male)", "english"),
    ("en-CA-ClaraNeural", "Clara (Canadian English HD Female)", "english"),
    ("en-IE-ConnorNeural", "Connor (Irish English HD Male)", "english"),
    ("en-IE-EmilyNeural", "Emily (Irish English HD Female)", "english"),
    ("en-IN-PrabhatNeural", "Prabhat (Indian English HD Male)", "english"),
    ("en-IN-NeerjaNeural", "Neerja (Indian English HD Female)", "english"),
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
    # Indian languages
    ("hi-IN-MadhurNeural", "Madhur (Hindi HD Male)", "hindi"),
    ("hi-IN-SwaraNeural", "Swara (Hindi HD Female)", "hindi"),
    ("mr-IN-ManoharNeural", "Manohar (Marathi HD Male)", "marathi"),
    ("mr-IN-AarohiNeural", "Aarohi (Marathi HD Female)", "marathi"),
    ("bn-IN-BashkarNeural", "Bashkar (Bengali HD Male, India)", "bengali"),
    ("bn-IN-TanishaaNeural", "Tanishaa (Bengali HD Female, India)", "bengali"),
    ("ta-IN-ValluvarNeural", "Valluvar (Tamil HD Male)", "tamil"),
    ("ta-IN-PallaviNeural", "Pallavi (Tamil HD Female)", "tamil"),
    ("te-IN-MohanNeural", "Mohan (Telugu HD Male)", "telugu"),
    ("te-IN-ShrutiNeural", "Shruti (Telugu HD Female)", "telugu"),
    ("gu-IN-NiranjanNeural", "Niranjan (Gujarati HD Male)", "gujarati"),
    ("gu-IN-DhwaniNeural", "Dhwani (Gujarati HD Female)", "gujarati"),
    ("kn-IN-GaganNeural", "Gagan (Kannada HD Male)", "kannada"),
    ("kn-IN-SapnaNeural", "Sapna (Kannada HD Female)", "kannada"),
    ("ml-IN-MidhunNeural", "Midhun (Malayalam HD Male)", "malayalam"),
    ("ml-IN-SobhanaNeural", "Sobhana (Malayalam HD Female)", "malayalam"),
    # Thai
    ("th-TH-NiwatNeural", "Niwat (Thai HD Male)", "thai"),
    ("th-TH-PremwadeeNeural", "Premwadee (Thai HD Female)", "thai"),
    # Icelandic
    ("is-IS-GunnarNeural", "Gunnar (Icelandic HD Male)", "icelandic"),
    ("is-IS-GudrunNeural", "Gudrun (Icelandic HD Female)", "icelandic"),
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
    "hindi": "hi-IN-MadhurNeural",
    "marathi": "mr-IN-ManoharNeural",
    "bengali": "bn-IN-BashkarNeural",
    "tamil": "ta-IN-ValluvarNeural",
    "telugu": "te-IN-MohanNeural",
    "gujarati": "gu-IN-NiranjanNeural",
    "kannada": "kn-IN-GaganNeural",
    "malayalam": "ml-IN-MidhunNeural",
    "thai": "th-TH-NiwatNeural",
    "icelandic": "is-IS-GunnarNeural",
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
    "hindi": "FluentVoice Pro में आपका स्वागत है! उच्च गुणवत्ता वाली प्राकृतिक आवाज़ सक्रिय है।",
    "marathi": "FluentVoice Pro मध्ये आपले स्वागत आहे! उच्च दर्जाचा नैसर्गिक आवाज सक्रिय आहे.",
    "bengali": "FluentVoice Pro-তে আপনাকে স্বাগতম! উচ্চমানের স্বাভাবিক কণ্ঠস্বর চালু আছে।",
    "tamil": "FluentVoice Pro-க்கு வரவேற்கிறோம்! உயர்தர இயல்பான குரல் இயக்கத்தில் உள்ளது.",
    "telugu": "FluentVoice Pro కు స్వాగతం! అధిక నాణ్యత గల సహజ స్వరం సక్రియంగా ఉంది.",
    "gujarati": "FluentVoice Pro માં આપનું સ્વાગત છે! ઉચ્ચ ગુણવત્તાવાળો કુદરતી અવાજ સક્રિય છે.",
    "kannada": "FluentVoice Pro ಗೆ ಸುಸ್ವಾಗತ! ಉತ್ತಮ ಗುಣಮಟ್ಟದ ಸಹಜ ಧ್ವನಿ ಸಕ್ರಿಯವಾಗಿದೆ.",
    "malayalam": "FluentVoice Pro-ലേക്ക് സ്വാഗതം! ഉയർന്ന നിലവാരമുള്ള സ്വാഭാവിക ശബ്ദം സജീവമാണ്.",
    "thai": "ยินดีต้อนรับสู่ FluentVoice Pro! เสียงพูดธรรมชาติคุณภาพสูงเปิดใช้งานแล้ว",
    "icelandic": "Velkomin í FluentVoice Pro! Náttúrulega röddin er virk og hljóðgæðin eru frábær.",
}

_BY_ID = {v: (label, fam) for v, label, fam in CATALOG}

_PREFIX_FAMILY = {
    "en-": "english", "he-": "hebrew", "ar-": "arabic", "es-": "spanish", "fr-": "french",
    "de-": "german", "it-": "italian", "pt-": "portuguese", "ru-": "cyrillic", "ja-": "cjk",
    "zh-": "chinese", "ko-": "korean", "hi-": "hindi", "mr-": "marathi", "bn-": "bengali",
    "ta-": "tamil", "te-": "telugu", "gu-": "gujarati", "kn-": "kannada", "ml-": "malayalam",
    "th-": "thai", "is-": "icelandic",
}


def current_id(voice: str) -> str:
    """Map a retired voice id to its replacement."""
    return RETIRED.get(voice, voice)


def label_for(voice: str) -> str:
    if is_local_hd(voice):
        from . import localtts
        return localtts.label(voice, LANGUAGES.get(family_of(voice), ""))
    return _BY_ID.get(current_id(voice), (voice, ""))[0]


def short_name(voice: str) -> str:
    """'Avri (Hebrew HD Male)' → 'Avri'."""
    return label_for(voice).split(" (")[0]


_OFFLINE_LANG = {"English": "english", "Hebrew": "hebrew", "Arabic": "arabic", "Spanish": "spanish",
                 "French": "french", "German": "german", "Italian": "italian", "Portuguese": "portuguese",
                 "Russian": "cyrillic", "Japanese": "cjk", "Chinese": "chinese", "Korean": "korean",
                 "Hindi": "hindi", "Marathi": "marathi", "Bengali": "bengali", "Tamil": "tamil",
                 "Telugu": "telugu", "Gujarati": "gujarati", "Kannada": "kannada", "Malayalam": "malayalam",
                 "Thai": "thai", "Icelandic": "icelandic"}


def family_of(voice: str) -> str:
    """Language family of a voice id (neural ids by locale prefix; Windows offline voices by
    the language in their description, e.g. 'Microsoft Asaf - Hebrew (Israel)'; else english)."""
    v = current_id(voice or "")
    if v in _BY_ID:
        return _BY_ID[v][1]
    if v in _LOCAL_FAMILY:
        return _LOCAL_FAMILY[v]
    for lang, fam in _OFFLINE_LANG.items():
        if f" - {lang} (" in v:
            return fam
    low = v.lower()
    for prefix, fam in _PREFIX_FAMILY.items():
        if low.startswith(prefix):
            return fam
    return "english"


_NEURAL_ID = re.compile(r"^[a-z]{2,3}-[A-Z]{2,4}-\w+Neural$")

# Offline HD voices (Piper / Kokoro, see local_catalog.py): id → language family.
_LOCAL_FAMILY = {row[0]: row[2] for row in local_catalog.PIPER_VOICES}
_LOCAL_FAMILY.update({f"kokoro:{name}": local_catalog.KOKORO_LANGS[name[0]][0]
                      for name, _ in local_catalog.KOKORO_VOICES})


def is_online(voice: str) -> bool:
    """True for Microsoft Edge neural voices: the text is sent to Microsoft's online service."""
    return bool(_NEURAL_ID.match(current_id(voice or "")))


def is_local_hd(voice: str) -> bool:
    """True for offline HD voices (Piper / Kokoro) that run on this PC."""
    return (voice or "").startswith(("piper:", "kokoro:"))


def is_offline(voice: str) -> bool:
    """True for Windows offline voices (SAPI5 / OneCore, e.g. 'Microsoft George - English
    (United Kingdom)' or legacy 'Zira'); False for Microsoft neural (cloud) voice ids and for
    offline HD voices (Piper / Kokoro, which have their own engine).
    Earlier versions only treated names containing "Desktop"/"SAPI" as offline, so OneCore
    voices were sent to the cloud service, failed, and fell back to Zira."""
    return not is_online(voice) and not is_local_hd(voice)


def is_multilingual(voice: str) -> bool:
    return "multilingual" in (voice or "").lower()


def can_read(voice: str, language: str) -> bool:
    """True when this voice reads `language` natively, so auto-routing should keep it."""
    fam = family_of(voice)
    if fam == language or SAME_SCRIPT.get(fam) == language:
        return True
    return is_multilingual(voice) and language in LATIN_FAMILIES and fam in LATIN_FAMILIES


def voices_for(family: str) -> list[tuple[str, str]]:
    """[(voice id, label)] for one language, in catalog order (Microsoft online voices)."""
    return [(v, label) for v, label, fam in CATALOG if fam == family]


def local_voices_for(family: str, installed_only: bool = True) -> list[tuple[str, str]]:
    """[(voice id, label)] of offline HD voices (Piper / Kokoro) for one language."""
    from . import localtts
    return [(v["id"], label_for(v["id"])) for v in localtts.voices_for(family)
            if not installed_only or localtts.is_installed(v["id"])]


def all_voices_for(family: str) -> list[tuple[str, str]]:
    """Online voices, then the downloaded offline HD voices, for one language."""
    return voices_for(family) + local_voices_for(family)


def sample_text(voice: str) -> str:
    return SAMPLE_TEXT.get(family_of(voice), SAMPLE_TEXT["english"])
