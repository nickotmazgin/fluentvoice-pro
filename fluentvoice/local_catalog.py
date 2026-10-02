"""Offline HD voices (Piper, Kokoro): what can be downloaded, from where, under which licence.

Pure data, shared by voices.py (labels, languages), localtts.py (download + speech) and
Settings (Voice Providers tab). Every file is pinned to its SHA-256, so a download that
was changed on the server, or damaged on the way, is rejected and never used.

Licences were checked voice by voice on each voice's model card (October 2026):
 - "free"     public domain, CC0, CC BY, CC BY-SA, Apache-2.0 or the Unlicense: usable for anything
              (CC BY / BY-SA ask that the source is credited; Settings and docs/VOICE_LICENSES.md do).
 - "personal" non-commercial licences, or recordings whose licence the author did not state:
              fine for reading text to yourself, not for publishing or selling the audio.
Voices whose recordings come from research-only datasets (e.g. Ryan, Lessac, HiFi-Captain) and
Kokoro voices named after other companies' voices (OpenAI, Google, Microsoft) are left out. Kokoro's
Japanese voices are left out too: through sherpa-onnx they skip kanji (checked by transcribing them).
"""

PIPER_BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main/"
PIPER_HOME = "https://github.com/OHF-Voice/piper1-gpl"
PIPER_VOICES_HOME = "https://huggingface.co/rhasspy/piper-voices"

# model → (onnx path in the voices repo, onnx sha256, onnx size, config sha256, config size)
PIPER_MODELS = {
    "en_US-joe-medium": ("en/en_US/joe/medium/en_US-joe-medium.onnx", "58afce0321b8d9c46d7cdf9c16500cc55a793b4220212dba6b70fb788b3baf06", 63201294, "3d6d5410b3795cb1950595247ef8f06190719e6fdbfa3a2356d8ec368e1aad33", 4794),
    "en_US-kristin-medium": ("en/en_US/kristin/medium/en_US-kristin-medium.onnx", "5849957f929cbf720c258f8458692d6103fff2f0e3d3b19c8259474bb06a18d4", 63531379, "5681426d4aead22195de70531eeeeddb46493cfaffc5764b2ea3db73428b651c", 4968),
    "en_US-norman-medium": ("en/en_US/norman/medium/en_US-norman-medium.onnx", "b9739443232a80a59c7d18810dd856899bf16a7964725f5ab81ea49b1351cb71", 63531379, "6c2db7f558a4a8deb9fe822583c1c5105f6c4e834dd0f9de8ad17a888ee9fe1d", 4968),
    "en_US-ljspeech-high": ("en/en_US/ljspeech/high/en_US-ljspeech-high.onnx", "5d4f08ba6a2a48c44592eed3ce56bf85e9de3dd4e20df90541ae68a8310c029a", 114199011, "7e1f4634af596d83cca997fb7a931ba80b70f8a316a2655ee69c55365e0ace14", 4970),
    "en_GB-cori-high": ("en/en_GB/cori/high/en_GB-cori-high.onnx", "470b4dd634c98f8a4850d7626ffc3dfc90774628eeef6605a6dd8f88f30a5903", 114219352, "9e7fb5b5671612c22f3c81cbe46c1ae87b031a4632bcb509e499dad6f1e2adec", 4963),
    "en_GB-alba-medium": ("en/en_GB/alba/medium/en_GB-alba-medium.onnx", "401369c4a81d09fdd86c32c5c864440811dbdcc66466cde2d64f7133a66ad03b", 63201294, "aa965a2f02ecced632c2694e1fc72bbff6d65f265fab567ca945918c73dd89f4", 4888),
    "en_GB-northern_english_male-medium": ("en/en_GB/northern_english_male/medium/en_GB-northern_english_male-medium.onnx", "57a219ae8e638873db7d18893304be5069c42868f392bb95c3ff17f0690d0689", 63201294, "69557ed3d974463453e9b0c09dd99a7ed0e52b8b87b64b357dbeeb2540a97d47", 4847),
    "es_ES-davefx-medium": ("es/es_ES/davefx/medium/es_ES-davefx-medium.onnx", "6658b03b1a6c316ee4c265a9896abc1393353c2d9e1bca7d66c2c442e222a917", 63201294, "0e0dda87c732f6f38771ff274a6380d9252f327dca77aa2963d5fbdf9ec54842", 4817),
    "es_MX-ald-medium": ("es/es_MX/ald/medium/es_MX-ald-medium.onnx", "019b3803293c93e34a206dd2e53a3889209a514e786fd7144f7b70196c579b63", 63201294, "5a71498158e04afc8099bfd019c7e87c68eb9d042505a2b1a87e5c1ac2b1a61d", 4878),
    "fr_FR-siwis-medium": ("fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx", "641d1ab097da2b81128c076810edb052b385decc8be3381814802a64a73baf99", 63201294, "39479916c2db192b5ac9764daddd0c744d83e023ad890c6976c0633ae4df8959", 4875),
    "fr_FR-upmc-medium": ("fr/fr_FR/upmc/medium/fr_FR-upmc-medium.onnx", "9abb3800c199148897a9ed64e100d224f3de83579f100044174ad19418f1786f", 76733615, "e8636ec15dfd5d72db37a02cb5320a20f2b8d339f2a0e4337da64c58a33a5868", 4996),
    "de_DE-thorsten-high": ("de/de_DE/thorsten/high/de_DE-thorsten-high.onnx", "9df1c43c61149ef9b39e618e2b861fbe41e1fcea9390b2dac62e8761573ea4f1", 113895201, "6de734444e4c3f9e33b7ebe2746dbc19b71e85f613e79c65acf623200b99a76a", 4875),
    "it_IT-paola-medium": ("it/it_IT/paola/medium/it_IT-paola-medium.onnx", "6fc918b5a0ea6137382833dddfa567bffbe6a5060c02043c87192ee59c04210c", 63511038, "aea19c0a7fce29fbc359b93f10e7902854401e4c95ae2ea328ae516b15d296cf", 7099),
    "pt_BR-faber-medium": ("pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx", "858555e3a064209c57088fe6bd70c4c3dc54d03eaa00c45d5ecaf43a33f95aa7", 63201294, "7e694de195ae3fc36dd732c445eb04fb49b649854893cb5506b978f0d50a1d6f", 4855),
    "pt_BR-cadu-medium": ("pt/pt_BR/cadu/medium/pt_BR-cadu-medium.onnx", "765f0809a6ea9035d4a6d0d008dbf8876e68b2dd32029312672fa8f405bdb535", 62950044, "5fe03aa3d4901880554905b12075713cd552598c8a350455a1ec73f8b4e6be19", 5040),
    "ru_RU-denis-medium": ("ru/ru_RU/denis/medium/ru_RU-denis-medium.onnx", "15fab56e11a097858ee115545d0f697fc2a316c41a291a5362349fb870411b0a", 63201294, "831c860dac0b5073eaa81610a0a638ec23d90a6cf8e5f871b4485c2cec3767c8", 4823),
    "ru_RU-dmitri-medium": ("ru/ru_RU/dmitri/medium/ru_RU-dmitri-medium.onnx", "f073356ebc4bd0f80c5af58df2953a5988bd5bdab1eb38635ce960b071fbefcb", 63201294, "667ef3117bc642c2892dff7690d8bdc8ca4228aeaa783b2dc1416df632855e0d", 4824),
    "mr_IN-google-medium": ("mr/mr_IN/google/medium/mr_IN-google-medium.onnx", "e1200d474a74ebd6d1737be2c7affe56f1f9efc18915d4595d7f5c2b15cf06f4", 76768179, "11055302ee1e3c9902e5e96c03cbfc0a9eec29b1b06b91ef52a3c66e9873edbb", 5467),
    "bn_BD-google-medium": ("bn/bn_BD/google/medium/bn_BD-google-medium.onnx", "f2e7518ed5534a755024a48c71b80bf617efaf12570bbdf3ce255a9526a8afd3", 76782515, "bc7e5e39e2a874bdad186620576ce18089b5a06c5645e258bcea3d56fdb11c0a", 5494),
    "te_IN-padmavathi-medium": ("te/te_IN/padmavathi/medium/te_IN-padmavathi-medium.onnx", "414aa5960d91ceb6e45bbdf8c27fdc71af09f205130d7be4e99470f3c2cfa57d", 63516050, "6c86e4ee99d379815f78a75f23cdad62ccf50370062dd915c233d6e22de7109f", 4974),
    "te_IN-venkatesh-medium": ("te/te_IN/venkatesh/medium/te_IN-venkatesh-medium.onnx", "dfaa5b7833cd48d946f3fe18c9c934aaa4e8590aac6922fddf34783a694c3c87", 63516050, "59bad556763d1f24b3434201d7bdee275bb1a70db3e1c65d38e6c3d39b224343", 4973),
    "is_IS-ugla-medium": ("is/is_IS/ugla/medium/is_IS-ugla-medium.onnx", "b43aef7648d13f68b6db0032d85716b82ca78716218a68442fd7f12444a73b24", 76495465, "0d7c1b26cdc54042c98a75ccc9d4e3528077178c56ad029b321944b6178f3277", 4163),
    "is_IS-bui-medium": ("is/is_IS/bui/medium/is_IS-bui-medium.onnx", "3a645b2d2850e4098f01f3765cece931836c03741e01a5cc514d09d39d37c05c", 76495465, "3cae728572fbb397713d047f2299247bb76b62639d9dfdcd65b26c578b8aba45", 4162),
    "he_IL-saspeech-medium": ("he/he_IL/saspeech/medium/he_IL-saspeech-medium.onnx", "3dc067debc9e782a8a0d095dbb58786648743d406366dcc2aa81009660873b4d", 63221984, "e9800a282a6cf2e44b3ad97f640b38e35ed246dfe070458d13bfcf206befc5bf", 5269),
    "ar_JO-kareem-medium": ("ar/ar_JO/kareem/medium/ar_JO-kareem-medium.onnx", "9e95cab07b679da603bba17c4dec7ab3111320571964ee95c0379603c086491e", 63201294, "ea6d9b9d9076dbdb6bf5c98c6a141ef154959d2359709b37855727964e7d6c4d", 5024),
    "ko_KR-kss-medium": ("ko/ko_KR/kss/medium/ko_KR-kss-medium.onnx", "624fd774e26895f24bebae1bd9a3379e3394baeade4b584924f83e414096e2c9", 63221984, "153b5619d0580f824a59108d83ca19434de410eb8e4fe80325b58684fdc8a1df", 5232),
    "ml_IN-meera-medium": ("ml/ml_IN/meera/medium/ml_IN-meera-medium.onnx", "0c3e730f8294286694cac5d33f4c94d050ed8ea74c5fd6d0d492d38cb57b5102", 62950044, "ad51935143f548d139a84c6ad1702b757cbceb52701167c0c1c98bebda7203e6", 5045),
    "ml_IN-arjun-medium": ("ml/ml_IN/arjun/medium/ml_IN-arjun-medium.onnx", "e881130516a874306972a07dcf262e6900140430c5658131121744a80ef3f11b", 62950044, "2804f070954e56545e88101b70331d444402187899d0a6ff03e5d44bee813245", 5044),
}

# (voice id, name, family, gender, region, licence kind, licence, source)
PIPER_VOICES = [
    ("piper:en_US-joe-medium", "Joe", "english", "Male", "US", "free",
     "CC0 1.0 (public domain dedication)",
     "https://github.com/OHF-Voice/voice-datasets"),
    ("piper:en_US-kristin-medium", "Kristin", "english", "Female", "US", "free",
     "Public domain (LibriVox recordings)",
     "https://librivox.org"),
    ("piper:en_US-norman-medium", "Norman", "english", "Male", "US", "free",
     "Public domain (LibriVox recordings)",
     "https://librivox.org"),
    ("piper:en_US-ljspeech-high", "LJ", "english", "Female", "US", "free",
     "Public domain (LJ Speech dataset)",
     "https://keithito.com/LJ-Speech-Dataset/"),
    ("piper:en_GB-cori-high", "Cori", "english", "Female", "UK", "free",
     "Public domain (LibriVox recordings)",
     "https://librivox.org"),
    ("piper:en_GB-alba-medium", "Alba", "english", "Female", "UK", "free",
     "CC BY 4.0",
     "https://datashare.ed.ac.uk/handle/10283/3270"),
    ("piper:en_GB-northern_english_male-medium", "Northern English", "english", "Male", "UK", "free",
     "CC BY-SA 4.0",
     "https://www.openslr.org/83/"),
    ("piper:es_ES-davefx-medium", "Dave", "spanish", "Male", "Spain", "free",
     "CC0 1.0 (public domain dedication)",
     "https://github.com/OHF-Voice/voice-datasets"),
    ("piper:es_MX-ald-medium", "Ald", "spanish", "Male", "Mexico", "free",
     "The Unlicense (public domain)",
     "https://huggingface.co/datasets/rmcpantoja/Ald_Mexican_Spanish_speech_dataset"),
    ("piper:fr_FR-siwis-medium", "Siwis", "french", "Female", "France", "free",
     "CC BY 4.0",
     "https://datashare.ed.ac.uk/handle/10283/2353"),
    ("piper:fr_FR-upmc-medium#jessica", "Jessica", "french", "Female", "France", "free",
     "CC BY-SA 4.0",
     "https://github.com/marytts/upmc-pierre-data"),
    ("piper:fr_FR-upmc-medium#pierre", "Pierre", "french", "Male", "France", "free",
     "CC BY-SA 4.0",
     "https://github.com/marytts/upmc-pierre-data"),
    ("piper:de_DE-thorsten-high", "Thorsten", "german", "Male", "", "free",
     "CC0 1.0 (public domain dedication)",
     "https://github.com/thorstenMueller/Thorsten-Voice"),
    ("piper:it_IT-paola-medium", "Paola", "italian", "Female", "", "free",
     "CC0 1.0 (public domain dedication)",
     "https://huggingface.co/datasets/paolapersico1/Voice-Dataset-Italian"),
    ("piper:pt_BR-faber-medium", "Faber", "portuguese", "Male", "Brazil", "free",
     "CC0 1.0 (public domain dedication)",
     "https://github.com/OHF-Voice/voice-datasets"),
    ("piper:pt_BR-cadu-medium", "Cadu", "portuguese", "Male", "Brazil", "free",
     "CC0 1.0 (public domain dedication)",
     "https://github.com/OHF-Voice/voice-datasets"),
    ("piper:ru_RU-denis-medium", "Denis", "cyrillic", "Male", "", "free",
     "CC0 1.0 (public domain dedication)",
     "https://github.com/OHF-Voice/voice-datasets"),
    ("piper:ru_RU-dmitri-medium", "Dmitri", "cyrillic", "Male", "", "free",
     "CC0 1.0 (public domain dedication)",
     "https://github.com/OHF-Voice/voice-datasets"),
    ("piper:mr_IN-google-medium#mrt_01523", "Crowdsourced", "marathi", "", "", "free",
     "CC BY-SA 4.0",
     "https://www.openslr.org/64/"),
    ("piper:bn_BD-google-medium#00737", "Crowdsourced", "bengali", "", "Bangladesh", "free",
     "CC BY-SA 4.0",
     "https://www.openslr.org/37/"),
    ("piper:te_IN-padmavathi-medium", "Padmavathi", "telugu", "Female", "", "free",
     "CC BY 4.0",
     "https://huggingface.co/datasets/ai4bharat/indicvoices_r"),
    ("piper:te_IN-venkatesh-medium", "Venkatesh", "telugu", "Male", "", "free",
     "CC BY 4.0",
     "https://huggingface.co/datasets/ai4bharat/indicvoices_r"),
    ("piper:is_IS-ugla-medium", "Ugla", "icelandic", "Female", "", "free",
     "CC BY 4.0 (Talrómur)",
     "http://hdl.handle.net/20.500.12537/104"),
    ("piper:is_IS-bui-medium", "Búi", "icelandic", "Male", "", "free",
     "CC BY 4.0 (Talrómur)",
     "http://hdl.handle.net/20.500.12537/104"),
    ("piper:he_IL-saspeech-medium", "Shaul", "hebrew", "Male", "", "personal",
     "Non-commercial use only (SASPEECH, Israeli Public Broadcasting Corporation)",
     "https://www.openslr.org/134/"),
    ("piper:ar_JO-kareem-medium", "Kareem", "arabic", "Male", "Jordan", "personal",
     "Recordings' licence not stated by the author: personal use only",
     "https://github.com/AliMokhammad/arabicttstrain"),
    ("piper:ko_KR-kss-medium", "KSS", "korean", "Female", "", "personal",
     "CC BY-NC-SA 4.0 (non-commercial)",
     "https://www.kaggle.com/datasets/bryanpark/korean-single-speaker-speech-dataset"),
    ("piper:ml_IN-meera-medium", "Meera", "malayalam", "Female", "", "personal",
     "IIT Madras Indic TTS licence: personal / non-commercial use",
     "https://www.iitm.ac.in/donlab/indictts"),
    ("piper:ml_IN-arjun-medium", "Arjun", "malayalam", "Male", "", "personal",
     "IIT Madras Indic TTS licence: personal / non-commercial use",
     "https://www.iitm.ac.in/donlab/indictts"),
]

KOKORO_HOME = "https://huggingface.co/hexgrad/Kokoro-82M"
KOKORO_PACK = {
    "url": "https://github.com/k2-fsa/sherpa-onnx/releases/download/tts-models/kokoro-multi-lang-v1_0.tar.bz2",
    "sha256": "c5f7e2d2caf082bc1d20fb70334a61d99d20b484500aad32e7cf84c128ea3298",
    "size": 349906910,
    "folder": "kokoro-multi-lang-v1_0",
    "licence": "Apache-2.0",
    # files inside the pack, hashed again before their first use in a session: (sha256, size)
    "files": {
        "model.onnx": ("b40f62b166ac8164b0627ef48a0b358eda0985e272fb03ef5252e7206305da11", 325560556),
        "voices.bin": ("1c5a5b983d3d50d8586d437a51f3faa2da7919ce76a013c081e65671a3447c29", 28200960),
        "tokens.txt": ("6ebb6bb288f20f3ae8d004d3c2ca27697da27c037d75e81a60e2a6a663f95425", 687),
    },
}

# Kokoro language prefix → (family, region, sherpa-onnx language code)
KOKORO_LANGS = {
    "a": ("english", "US", "en-us"),
    "b": ("english", "UK", "en-gb-x-rp"),
    "e": ("spanish", "Spain", "es"),
    "f": ("french", "France", "fr"),
    "h": ("hindi", "", "hi"),
    "i": ("italian", "", "it"),
    "p": ("portuguese", "Brazil", "pt-br"),
}

# (speaker name, speaker id in the pack). First letter = language, second = f(emale) / m(ale).
KOKORO_VOICES = [
    ("af_heart", 3), ("af_bella", 2), ("af_nicole", 6), ("af_sarah", 9), ("af_jessica", 4), ("af_river", 8),
    ("am_adam", 11), ("am_michael", 16), ("am_eric", 13), ("am_liam", 15),
    ("bf_alice", 20), ("bf_emma", 21), ("bf_isabella", 22), ("bf_lily", 23),
    ("bm_daniel", 24), ("bm_george", 26), ("bm_lewis", 27),
    ("ef_dora", 28), ("em_alex", 29),
    ("ff_siwis", 30),
    ("hf_alpha", 31), ("hf_beta", 32), ("hm_omega", 33), ("hm_psi", 34),
    ("if_sara", 35), ("im_nicola", 36),
    ("pf_dora", 42), ("pm_alex", 43),
]
