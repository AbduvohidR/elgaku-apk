"""
ELGAKU to'liq server — BITTA FAYL (sayt + musiqa + AI).
Joylash: GitHub repo root'iga shu server.py ni qo'ying, deploy qiling.
"""
import json, re
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
ROOT = Path(__file__).parent
MUSIC_DIR = ROOT / "music"

KB_JSON = r'''
{
  "meta": {
    "app": "ELGAKU",
    "package": "uz.elgaku.app",
    "version": "4.0.0",
    "language": "uz",
    "type": "knowledge_base",
    "style": "keep_like_coach",
    "description": "ELGAKU AI murabbiy baza — to'liq sport ta'limoti + reasoning. Serverda LLM system prompt sifatida.",
    "created": "2026-10-13"
  },
  "system_prompt": "Sen ELGAKU AI murabbiyisan — Keep ilovasidagi shaxsiy murabbiy: samimiy, quvnoq, motivatsion, o'zbekcha, qisqa va amaliy. Emoji ishlat (🏃‍♂️💪🔥). FIYRLASH: javobdan oldin ichki o'yla — foydalanuvchi darajasi, maqsadi, yetarli ma'lumot; yetishmasa BITTA aniq savol. Javob: 1) samimiy kirish; 2) sabab-asos; 3) aniq qadamlar (5-6 qator); 4) motivatsion yakun. Og'riq/jarohatda 'to'xtang, shifokor' de. Hech qachon 'bilmayman' demo — umumiy xavfsiz tavsiya ber. Raqamlarni asosla. 'sen' deb murojaat qil.",
  "reasoning_rules": [
    "10% qoidasi: haftalik hajm 10% dan oshmasin.",
    "Har hafta kamida 1 dam kuni rejalashtir.",
    "Jarohat/kuchli og'riq — to'xtash va shifokor.",
    "Foydalanuvchi darajasini aniqlashtir: boshlovchi/o'rta/tajribali.",
    "Ma'lumot yetishmasa — taxmin qilma, bitta savol ber.",
    "Yangi narsani (ovqat, jihoz, jadval) poyga kuni sinama — mashqda sinov."
  ],
  "categories": [
    {
      "id": "persona",
      "title": "Salomlashish",
      "qa": [
        {"q": ["salom", "hello", "hi", "assalomu alaykum"], "a": "Salom! 👋 Men sizning shaxsiy yugurish murabbiyingizman. 🏃‍♂️ Bugun nima ustida ishlaymiz?\n\n- 'Bugun nima qilay?' — mashq tanlayman\n- 'Menga reja tuz' — to'liq jadval\n- 'Texnika maslahat' — uslubni tuzataman 💪"},
        {"q": ["rahmat", "yaxshi", "zo'r"], "a": "Arzimaydi! 😊 Har qadamda siz bilanman. Men sizga ishonaman! 🔥"},
        {"q": ["sen kimsan", "siz kimsiz"], "a": "Men ELGAKU AI murabbiyiman 🏃‍♂️ — cho'ntak treneringiz. Texnika, reja, ovqatlanish, jarohat oldini olish va motivatsiya bo'yicha yordam beraman. Maqsadni ayting — boshlaymiz! 💪"}
      ]
    },
    {
      "id": "texnika",
      "title": "Texnika va biomexanika",
      "qa": [
        {"q": ["kadans", "qadam tezligi", "180"], "a": "Kadans — bir daqiqadagi qadamlar. 👣 Maqsad 170-180/daq. Qisqa qadam = tizza yuki kam = jarohat kam. Musiqa 180 BPM topib, har beshikda qadam bosing. 4-6 haftada o'zgaradi."},
        {"q": ["foot strike", "oyoq tushishi", "tovon"], "a": "Oyoq gavda ostiga tushsin, oldinga cho'zilmasin. 👟 O'rta/panja yoki yumshoq tovon. Overstriding (oldinga cho'zish) — tizzaga tormoz zarbasi. Kadansni oshirsangiz — o'zi to'g'rilanadi."},
        {"q": ["gavda holati", "to'g'ri turish"], "a": "Gavda 5-10° oldinga egilgan, yelkalar bo'sh, qorin tortilgan, bosh tojdan tortilgandek. 🧍 Qo'llar 90°, oldinga-orqaga. To'g'ri holat = o'pka ochiq = nafas oson."},
        {"q": ["nafas olish", "qorin nafasi"], "a": "Ritm: 2 qadam olib, 2 qadam chiqaring (2:2). 🫁 Qorin bilan nafas oling. Tez nafas — temp sekin. Yelka bo'sh bo'lsin."},
        {"q": ["qo'l harakati"], "a": "Qo'llar 90°, bilak gavda yaqinida, elkadan oldinga-orqaga. 🤾 Chap qo'l - o'ng oyoq. Keng chapga-o'ngga silkitish — energiya isrofi."}
      ]
    },
    {
      "id": "drills",
      "title": "Texnika drill'lari",
      "qa": [
        {"q": ["a-skip", "b-skip", "drill nima"], "a": "Drill'lar — texnika o'rgatuvchi mashqlar! 🤸 Har yugurish oldidan 5-10 daqiqa:\n\n- **A-skip**: bir oyoqda sakrab, tizzani ko'tarish, panja bilan yerga urish\n- **B-skip**: A-skip + oyoq oldinga cho'zish\n- **High knees**: baland tizza yugurish\n- **Butt kicks**: tovonni dumbaга tegizish\n- **Carioca**: yon tomonga o'zaro oyoq kesish\n\nBu — kadans va oyoq tezligini oshiradi. Haftada 2 marta!"},
        {"q": ["strideout", "qisqa tez uchish"], "a": "Strideout — 80-100 metr tez (lekin maksimal emas) yugurish, orasida to'liq dam. ⚡\n\nHar yengil mashq oxirida 4-6 marta. Bu — muskullarni tezlikka o'rgatadi, yugurishni 'yonq'iradi'. Juda oson tuyuladi, lekin juda foydali! 🔥"},
        {"q": ["fartlek", "erkin tezlik almashish"], "a": "Fartlek — shvedcha 'o'yin tezligi'. 🏃 Xohlagan joyda tez, xohlaganda sekin: daraxtgacha tez, svetoforgacha sekin.\n\nStrukturasiz, qiziqarli, zerikkanlar uchun ideal. Yugurishni o'yinga aylantiradi! 🌈"}
      ]
    },
    {
      "id": "temp_turlari",
      "title": "Trenirovka temp turlari",
      "qa": [
        {"q": ["easy run", "yengil yugurish", "2 zona"], "a": "Easy (2 zona) — barcha yuguruvchilarning 80% mashqi! 💨 Suhbatlasha oladigan temp, 60-70% HR. Bu yerda yog' yonadi, tiklanadi, forma quriladi.\n\nKo'pchilik xato: hammasini juda tez qiladi. Aksin — sekin bo'lsin, ko'p bo'lsin!"},
        {"q": ["long run", "uzun yugurish", "chorshanba yakshanba"], "a": "Long run — haftadagi eng uzun mashq (2 soatgacha). 🏃\n\nMaqsad: chidamlilik, ongni 'uzunga' o'rgatish, glikogen zaxiralash. Temp juda sekin (easy'dan ham sekinroq!). Har 7 kunda 10-15% oshiring. Oxirgi 3 hafta poyga oldidan — kamaytiring."},
        {"q": ["tempo run", "threshold", "laktat chegarasi"], "a": "Tempo (threshold) — 'konforli qattiq' temp, 20-30 daqiqa uzluksiz. 🎯 Bu laktat chegarasida. Gapira olmaysiz, lekin qichqirmaysiz. Haftada 1 marta — tezlikni oshiradi."},
        {"q": ["interval", "interval mashq"], "a": "Interval — qisqa tez bo'laklar + dam. ⚡ Masalan: 4×400m tez, orasida 2 daq yurish. VO2max'ni oshiradi. Haftada 1 marta, undan ko'p emas — qattiq yuk!"},
        {"q": ["80/20 qoida", "polarized training"], "a": "80/20 — eng kuchli tamoyil! 📊\n\n80% mashq — juda yengil (2 zona), 20% — qattiq (4-5 zona). O'rtacha (3 zona) minimal bo'lsin.\n\nTadqiqotlar: shunday qilgan yuguruvchilar eng tez natija beradi. O'rtada 'botqoq' zona xavfli — ko'pchilik shu tuzoqqa tushadi. Sekinni sekin, qattiqni qattiq qiling!"}
      ]
    },
    {
      "id": "jarohat",
      "title": "Jarohatlar",
      "qa": [
        {"q": ["tizza og'riyapti", "tendonit"], "a": "Tizza og'rig'i: yugurishni to'xtang, dam, muz. 🦵 Sabab: ortiqcha hajm, yomon krossovka, zaif dumba. Skvater va clamshell mashq qiling. 2 hafta o'tmasa — shifokor."},
        {"q": ["boldir", "shin splint"], "a": "Shin splint: to'xtang, devorga cho'zing, yumshoq yerda yuguring. 🦶 Tovon ko'tarish 3×15. Qattiq yo'lda yugurmang."},
        {"q": ["plantar fasiit", "tovon"], "a": "Tovon tagi: ertalab turmasdan oyoqni massaj qiling, tennis to'pi dumalang. 🦶 Yumshoq taglik. Oyoq panjasini kuchaytiring."},
        {"q": ["bel og'rig'i"], "a": "Bel: zaif yadro. Planka, qorin press, gavda holati. 🚶 Yumshoq krossovka. Og'riqda yugurmang."},
        {"q": ["side stitch", "yon kramp", "qorin sanchiq"], "a": "Yon sanchig'i (side stitch) — juda keng tarqalgan! 🤕\n\nSabab: ovqatdan keyin tez yugurish, diafragma spazmi. Yechim:\n1. To'xtang yoki sekinlang\n2. Barmoqlar bilan sanchiq joyni bosing\n3. Chuqur nafas oling\n4. Oldinga egilib, nafas chiqaring\n\nOldini olish: mashqdan 2 soat oldin og'ir ovqat yemang, suvni kam-ko'p iching."},
        {"q": ["ishqalanish", "chafing", "qabariq", "blister"], "a": "Ishqalanish va qabariq — noqulay, lekin oldini olsa bo'ladi! 🩹\n\n- Sintetik kiyim kiying (paxta emas)\n- Muammo joyga vazelin yoki maxsus balzam surting\n- Yangi krossovkani uyda 'yaltirating'\n- Paypoqlar tikuvsiz, sportga mos bo'lsin\n- Qabariqni teshmang — ustiga plaster qo'ying"}
      ]
    },
    {
      "id": "issiq_tiniq",
      "title": "Ilishing, sovutish, cho'zish",
      "qa": [
        {"q": ["warmup", "isinish"], "a": "5-10 daqiqa: sekin yugurish + dinamik cho'zish (tizza ko'tarish, oyoq orqaga). 🔥 Statik cho'zish emas — dinamik. Bu jarohat oldini oladi."},
        {"q": ["cool down", "sovutish"], "a": "5-10 daqiqa sekin yurish + statik cho'zish (30 soniya). ❄️ Sut kislota chiqadi, ertangi kun qotmaydi."},
        {"q": ["cho'zish", "stretching"], "a": "Mashqdan keyin cho'zing: son oldi/orqa, boldir, dumba, 30 soniya × 2. 🤸 Sakramang, og'riq emas kuchlanish bo'lsin. Haftada 3 marta."}
      ]
    },
    {
      "id": "kuch",
      "title": "Kuch va cross-training",
      "qa": [
        {"q": ["kuch mashqlari", "skvater", "gantel"], "a": "Haftada 2 marta: skvater 3×12, lunge 3×10, planka 3×30-60s, tovon ko'tarish 3×15. 💪 Kuchli mushak = yaxshi texnika = kam jarohat."},
        {"q": ["cross training", "velosiped", "suzish"], "a": "Dam kunlarida: velosiped, suzish, ellipsoid. 🚴🏊 Yurak ishlaydi, mushak tiklanadi, zarba yo'q. Haftada 1-2 marta."},
        {"q": ["yadro", "core", "planka"], "a": "Planka — eng oddiy va eng foydali. 3×30-60 soniya. 🎯 Kuchli core = to'g'ri holat = bel himoyalangan."},
        {"q": ["glut aktivlash", "clamshell", "dumba"], "a": "Zaif dumba — tizza va bel og'rig'ining asosiy sababi! 🔑\n\nMashqlar: clamshell (yotib, tizzani ochish), glute bridge, side plank. Har kuni 5 daqiqa. Yugurishdan oldin 1 daqiqa 'faqat dumba' ishga tushiring — bu 'dummy' faollashtirish."}
      ]
    },
    {
      "id": "poyga",
      "title": "Poyga strategiyasi",
      "qa": [
        {"q": ["poyga kuni", "start oldidan"], "a": "Kecha: ko'p uglevod. Ertalab: banan + yengil nonushta. Startdan 30 daq oldin: 10 daq isinish. 🏁 Birinchi km SEKIN boshlang! O'z tempingiz, boshqalarga ergashmang."},
        {"q": ["pacing", "negativ split"], "a": "Birinchi yarim sekin, ikkinchi yarim tez — negativ split. 🚩 Bu professional taktika. Birinchi km rejadan 10-15 soniya sekin bo'lsin."},
        {"q": ["tapering", "poyga oldin hajm"], "a": "2 hafta oldin hajm 60%, 1 hafta oldin 40%. Tezlikni saqlang. 📉 Tana tiklanadi, tetik bo'lasiz. Ko'p yugurish poyga oldidan — ZARARLI."},
        {"q": ["marafon ovqat", "gel", "yonilg'i"], "a": "Har 45 daq 30-60g uglevod (gel, banan). 🍌 Har 20 daq 150-200ml suv. Mashqda qaysi gel'ga o'rgansangiz — poyga kuni ham shuni. Yangi narsa sinamang!"},
        {"q": ["10k reja", "10 km"], "a": "10K — ajoyib masofa! 🏁 6 hafta:\n- 1-2 hafta: 3×3km easy\n- 3-4 hafta: 4km + 1km interval\n- 5 hafta: 6km uzun + 3×400m\n- 6 hafta: 10K sinov\n\nHaftada 3-4 mashq. Boshlang'ich maqsad — 50-60 daqiqa. 💪"},
        {"q": ["yarim marafon", "21k"], "a": "Yarim marafon — 10 hafta. 🏃\n\nHar hafta: 3-4 mashq + bitta long run (8→16 km). Haftada 1 interval, 1 tempo. Long run temp juda sekin bo'lsin.\n\nOxirgi 2 hafta tapering. Siz tayyor bo'lasiz!"}
      ]
    },
    {
      "id": "uyqu_tiklash",
      "title": "Uyqu va tiklanish",
      "qa": [
        {"q": ["necha soat uxlash", "uyqu"], "a": "7-9 soat. 😴 Chuqur uyquda mushak o'sadi, gormon balanslanadi. Yotishdan 1 soat oldin telefon — yo'q. Xona salqin, qorong'i."},
        {"q": ["aktiv tiklanish", "aktiv dam"], "a": "Dam kuni: 20-30 daq sekin yurish yoki cho'zish. 🚶 Qon aylanishi yaxshilanadi, mushak qotmaydi."},
        {"q": ["domlariş", "mushak qotishi", "DOMS"], "a": "2 kun keyin qotish — normal. 🦵 Yengil harakat, issiq dush, massaj. 3-4 kunda o'tadi. Kuchli og'riq — ortiqcha yuk belgisi."},
        {"q": ["ko'pikli rolik", "foam roller", "massaj qurol"], "a": "Ko'pikli rolik — mushakni 'yopib ochadi'! 🧑\u200d🦯\n\nHar kuni yoki mashqdan keyin 5-10 daqiqa: son oldi/orqa, boldir, dumba ustida dumalang. Og'riqli nuqtada 30 soniya turing. Bu qon aylanishini oshiradi, kuchlanishni oladi. Massaj quroli ham xuddi shu maqsadda."},
        {"q": ["sovuq vanna", "ice bath", "krioterapiya"], "a": "Sovuq vannalar — ziddiyatli mavzu. 🧊\n\nQisqa muddatli yengillik beradi, lekin mushak o'sishini susaytirishi mumkin (shunday degan tadqiqotlar bor). Muntazam emas — faqat katta musobaqadan keyin foydalaning. Har kungi odat qilmang! Yengil issiq dush xavfsizroq."}
      ]
    },
    {
      "id": "jihoz",
      "title": "Krossovka va jihoz",
      "qa": [
        {"q": ["qachon almashtirish", "necha km"], "a": "600-800 km. 👟 Amortizatsiya yo'qolsa — tizza og'riydi. Taglik tekislandi, yon yorildi — almashtiring."},
        {"q": ["qanday tanlash", "yo'l trail"], "a": "Yo'l uchun yumshoq road, tog' uchun chuqur protektorli trail. 👟 Kechqurun kiyib ko'ring (oyoq shishgan). Barmoqlarga joy."},
        {"q": ["carbon plate", "uglerodli", "tezkor krossovka"], "a": "Uglerod-plitali krossovkalar 2-4% tezroq qiladi! 🏅\n\nLekin: qattiq, o'rganish kerak, qimmat. Poygaga 3-4 hafta qolganda sinab ko'ring — poyga kuni EMAS. Mashqda oddiy krossovkada yuguring, poyga kuni 'quvvatli'larni kiying."},
        {"q": ["kiyim", "kiyim haqida"], "a": "Sintetik, yengil, tikuvsiz. Paxta — yo'q (ho'l bo'ladi, ishqalanadi). 🧢 Issiq havoda ochiq rang, quyoshdan himoya kremi. Qishda qatlamli."}
      ]
    },
    {
      "id": "ovqatlanish",
      "title": "Ovqatlanish",
      "qa": [
        {"q": ["oqsil", "protein"], "a": "1.6 g/kg. Tuxum, tovuq, baliq, loviya, tvorog. 🥩 Har ovqatda 20-30g. Mashqdan keyin 30 daq ichida oqsil+uglevod."},
        {"q": ["uglevod", "karbo loading"], "a": "5-7 g/kg. Guruch, makaron, non, meva. 🍚 Poygadan 2 kun oldin 7-10 g/kg — glikogen zaxira."},
        {"q": ["qahva", "kofein"], "a": "Mashqdan 30-45 daq oldin 1-2 kichik qahva chidamlilikni 2-5% oshiradi. ☕ Ko'p bo'lmasin. Poygaga odatlangan miqdorda."},
        {"q": ["vitamin", "temir", "anemiya"], "a": "Temir tanqisligi — yuguruvchilarda keng tarqalgan! 🩸\n\nAyollar va uzoq yuguruvchilarda (foot-strike qizil qon hujayralarini buzadi) xavf yuqori. Belgilar: charchoq, holsizlik, sovuqqonlik. Qon tahlili qiling, temir va C vitamini oling. Shifokor nazoratisiz ko'p temir yemang!"},
        {"q": ["elektrolit", "natriy", "tuz"], "a": "Uzoq mashqda (90 daq+) ter bilan tuz ketadi. 🧂\n\nKo'p yugurishda oddiy suv yetarli emas — elektrolitli ichimlik yuzasidan bir chimdim tuz. Yengil kramplar — natriy yetishmasligi belgisi. Issiq havoda ayniqsa muhim."},
        {"q": ["qo'shimcha", "kreatin"], "a": "Qo'shimchalar — muvozanatli ovqat o'rnini bosmaydi. 💊 Asosiy: D, temir, magniy. Kreatin — kuch uchun. Shifokor bilan maslahat."}
      ]
    },
    {
      "id": "havo",
      "title": "Ob-havo va balandlik",
      "qa": [
        {"q": ["issiqda", "heat"], "a": "Erta tong/kechqurun, tempni 1 daq/km sekinlatish. 🌡️ Har 15 daq suv. Bosh aylansa — to'xtang. Issiqlik urishi xavfli!"},
        {"q": ["sovuqda", "qish"], "a": "3 qatlam: ichki namlik oluvchi, o'rta izolyatsiya, tashqi shamol to'sar. 🧣 Yuz, qo'l himoyalansin. 0° dan sovuqda qisqartiring."},
        {"q": ["balandlik", "altitude"], "a": "1500m+ da kislorod kamroq. 🏔️ 1-2 hafta moslashish davri. Tempni 20-30% sekinlatib, masofani kamaytiring. Poyga uchun 2 hafta oldin yetib boring."},
        {"q": ["tungi yugurish", "kechqurun"], "a": "Tungi yugurish — xavfsizlik muhim! 🌙\n\n- Yorqin/reflektorli kiyim kiying\n- FonaR yoki chamrasiz yorqin telefon\n- Odam ko'p joyda, yaxshi yoritilgan yo'lda yuguring\n- Quloqchinlarni bitta quloqqa taqing (atrofni eshiting)\n- Do'stingizga marshrutni xabar qiling"}
      ]
    },
    {
      "id": "psixologiya",
      "title": "Sport psixologiyasi",
      "qa": [
        {"q": ["chidash", "qiyin daqiqa"], "a": "Kichik maqsadlarga bo'ling: svetoforgacha, daraxtgacha. 🧠 Nafas ritmini eslang. Ichki ovoz: 'Men buni qila olaman'. Professionalar ham shu daqiqalarni boshdan kechiradi."},
        {"q": ["zerikish", "motivatsiya yo'q"], "a": "Marshrut almashtiring, musiqa, intervalli, do'st, kichik poyga. 🌈 Tana xilma-xillikni yaxshi ko'radi."},
        {"q": ["vizualizatsiya", "meditatsiya"], "a": "Kuniga 5 daqiqa: finishni, lenta uzayotganni tasavvur qiling. 🎬 Miya farqlamaydi — haqiqatmi yoki xayol. Natija beradi."},
        {"q": ["rekord qo'yish", "shaxsiy rekord", "PR"], "a": "Shaxsiy rekord — bu o'zingiz bilan bellashuv! 🏆 Oldingi natijangizga qarang, bir necha hafta ixtisoslashtiring. PR keladi — shoshmang. Jamoaviy yuguruvchilar tezroq bo'ladi."}
      ]
    },
    {
      "id": "ayollar",
      "title": "Ayollar yugurishi",
      "qa": [
        {"q": ["hayz davri", "menstruatsiya", "yugurish"], "a": "Hayz davrida yugurish — individual. 🩸\n\nKo'pchilikda yengil yugurish og'riqni kamaytiradi (endorfin). Birinchi kunlarida o'zingizni past tutsangiz — tempni sekinlang, masofani kamaytiring. Hech qanday 'siz yugura olmaysiz' degan qoida yo'q — tana sezgiingizga ishoning. Og'riq kuchli bo'lsa — dam. Temir tanqisligini kuzating!"},
        {"q": ["homiladorlik", "homilador yugurish"], "a": "Homiladorlik — bu mutlaqo shifokor mavzusi! 🤰\n\nUmumiy tavsiya: oddiy, kam ta'sirli yugurish, qorniga qulay kiyim, yetarli kaloriya. Lekin HAR doim akusher bilan maslahatlashing — har bir holat individual. Pastki bosim, qorindi og'rig'i yoki qon bo'lsa — darhol to'xtang."},
        {"q": ["40 yoshdan keyin", "masters runners"], "a": "40+ yoshda yugurish — eng yaxshi investitsiya! 👵👴\n\nFarqlar: tiklanish sekinroq (1-2 kun ko'proq), bo'g'imlarga g'amxo'rlik, kuch mashqlari ZARUR (mushak massasi yosh bilan kamayadi). Xoch tayyorlanish va cho'zishga ko'proq vaqt bering. Siz tengdoshlaringizdan 10 yosh yosh ko'rinasiz! 🔥"}
      ]
    },
    {
      "id": "overtrening",
      "title": "Overtrening sindromi",
      "qa": [
        {"q": ["overtrening", "haddan tashqari", "doimiy charchoq"], "a": "Overtrening — bu siz o'ylagandan tezroq keladi! ⚠️\n\nBelgilar:\n- Doimiy charchoq, uyqu buzilishi\n- Tinch HR 5-10 urush ko'tarilgan\n- Hissiy befarqlik, motivatsiya yo'q\n- Ishlash pasaygan, shamollash tez-tez\n\nYechim: 1-2 hafta yengil yugurish yoki dam. Kichik hajm bilan qayting. 'Ko'p = yaxshi' emas, 'barqaror = yaxshi'."},
        {"q": ["resting hr", "tinch urish", "hrv"], "a": "Ertalab turganingizda tinch HR ni o'lchang. 📉\n\n- 5-10 urush ko'tarilgan = charchoq yoki kasallik boshlanishi\n- Pasaygan = forma yaxshilanmoqda\n- HRV (yurak urish o'zgaruvchanligi) — tiklanish ko'rsatkichi\n\nBularni kuzating. Tana signallariga quloq soling!"}
      ]
    },
    {
      "id": "trekmill",
      "title": "Trekmill va texnikalar",
      "qa": [
        {"q": ["trekmillada yugurish", "yugurish yo'lagi"], "a": "Trekmill — ob-havo yomonida qutqaruvchi! 🎢\n\n- Nishabni 1-2% qo'ying (oynalikni kompensatsiya qiladi)\n- Bo'sh joy qoldiring, harakat markazida turing\n- Yon tomonga qaramang (boshi aylanadi)\n- Sekin boshlang, sekin tugating\n\nKilometrga qarang — vaqt tezroq o'tadi, lekin tashqaridagi kabi shamol/qiyinchilik yo'q."},
        {"q": ["gps soat", "watch", "aniqlik"], "a": "GPS soat — foydali, lekin mukammal emas. ⌚\n\n- Yugurishdan oldin 1 daq tashqarida turing (sun'iy yo'ldosh topish)\n- Zich bino/daraxtlarda xato bo'ladi\n- Kadans va HR bilagingizdagi soatdan biroz kechikadi\n- Harakatlar oralig'ida qo'lni silkitib turing"}
      ]
    },
    {
      "id": "qaytish",
      "title": "Tanaffusdan keyin",
      "qa": [
        {"q": ["uzilishdan keyin qaytish", "kasallik", "vaqt yo'q edi"], "a": "Tanaffusdan keyin — hech qachon avvalgi hajm bilan boshlamang! 🔄\n\n1-2 hafta: hajmning 40-50%, 3-4 hafta: 60-70%, 5-6 hafta: 80%.\n\nTana 'unutilgan' — mushak xotirasi bor, lekin yurak-bag'ir moslashuvi sekin. Shoshmang! 4-6 haftada siz avvalgi darajaga qaytasiz. Birinchi 2 hafta juda yengil bo'lsin."},
        {"q": ["kasallikdan keyin", "gripp", "o'pka"], "a": "Kasallikdan keyin — bo'y qoidasi! 🤒\n\nAgar simptomlar bo'y (bo'yin) dan past bo'lsa (tomoq, yo'tal) — yengil yugurish mumkin. Bo'yin dan past (ko'krak, isitma, butun tana og'rig'i) — to'liq dam. Isitma tushganidan keyin kamida 3-5 kun kuting. Yurakka zarar bermang!"}
      ]
    },
    {
      "id": "jamoa",
      "title": "Jamoa va etiket",
      "qa": [
        {"q": ["yugurish klubi", "guruh", "do'st bilan"], "a": "Guruhda yugurish — motivatsiya va xavfsizlik! 👫\n\nTadqiqotlar: guruh bilan mashq qilganlar 2 barobar barqaror. Mahalliy klub toping, ijtimoiy tarmoqlarda qidiring. Yangi do'stlar, birgalikda poygalar. Yolg'iz zerikkanlar uchun — eng yaxshi dori."},
        {"q": ["yugurish etiket", "yo'lda"], "a": "Yo'lda odob: 🚦\n\n- Yugurishga qarshi yo'nalishda yuring (avtomobilni ko'rasiz)\n- Chorrahalarda to'xtang, qoidaga bo'ysuning\n- Itni qisqa bog'lab, boshqalarga to'sqinlik qilmang\n- Quloqchin baland emas — atrofni eshiting\n- Boshqa yuguruvchiga salom bering — bu an'ana! 👋"}
      ]
    },
    {
      "id": "nosozliklar",
      "title": "Texnik yordam",
      "qa": [
        {"q": ["gps ishlamayapti", "lokatsiya"], "a": "Aniq joylashuv ruxsati, ochiq osmon, 20 soniya. 🛰️ Bino ichida zaif bo'ladi. Ochiq maydonga chiqing."},
        {"q": ["ai server", "internet"], "a": "AI javoblari internet orqali. 🌐 Aloqani tekshiring, 1-2 daq kuting. Asosiy funksiyalar oflayn ishlaydi."}
      ]
    }
  ]
}

'''

KB = json.loads(KB_JSON)
QA_INDEX = []
for cat in KB.get("categories", []):
    for item in cat.get("qa", []):
        kws = set()
        for q in item.get("q", []):
            for w in re.findall(r"[a-z']+", q.lower()):
                if len(w) >= 3:
                    kws.add(w)
        QA_INDEX.append({"kws": kws, "answer": item.get("a", "")})

def tokenize(text):
    return set(w for w in re.findall(r"[a-z']+", text.lower()) if len(w) >= 3)

def best_reply(message):
    msg = tokenize(message)
    if not msg:
        return "Salom! 👋 Men sizning shaxsiy murabbiyingizman. 'Bugun nima qilay?' deb yozing."
    best_score, best_answer = 0, None
    for e in QA_INDEX:
        s = len(msg & e["kws"])
        if s > best_score:
            best_score, best_answer = s, e["answer"]
    if best_answer and best_score >= 1:
        return best_answer
    return ("Tushundim! 🤔 Bu savolni hozircha topa olmadim. Lekin yordam bera olaman:\n\n"
            "- 'Bugun nima qilay?' — mashq tanlayman\n"
            "- 'Menga haftalik reja tuz' — to'liq jadval\n"
            "- 'Texnika maslahat' — yugurish uslubi\n"
            "- 'Motivatsiya kerak' — sizni ruhlantiraman 💪")

@app.get("/api/apk/music")
def list_music():
    songs = []
    if MUSIC_DIR.exists():
        for f in sorted(MUSIC_DIR.iterdir()):
            if f.is_file() and f.suffix.lower() in (".mp3", ".m4a", ".wav", ".ogg"):
                songs.append({"id": f.stem, "title": f.stem.replace("_", " "), "url": f"/music/{f.name}"})
    return jsonify({"songs": songs, "count": len(songs)})

@app.post("/api/ai/chat")
def ai_chat():
    data = request.get_json(silent=True) or {}
    msg = (data.get("message") or "").strip()
    if not msg:
        return jsonify({"reply": "Iltimos, savol yozing! 👋"})
    return jsonify({"reply": best_reply(msg)})

@app.get("/")
def index():
    idx = ROOT / "index.html"
    if idx.exists():
        return send_from_directory(ROOT, "index.html")
    return "ELGAKU server ishlayapti ✅"

@app.get("/<path:path>")
def static_files(path):
    full = ROOT / path
    if full.is_file():
        return send_from_directory(ROOT, path)
    return "Not found", 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
