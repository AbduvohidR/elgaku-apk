#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ELGAKU server — static fayllar + SQLite API (operator paneli uchun).
Ishga tushirish:  python server.py   (http://localhost:8000)
"""
import json
import datetime
import os
import socket
import sqlite3
import re
import sys
import time
import random
import mimetypes
import urllib.parse
import base64
import io
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

ROOT = os.path.dirname(os.path.abspath(__file__))
# Lokalda elgaku.db yonma-yon, serverda (fly.io) ELGAKU_DB env orqali volume'ga ko'rsatiladi
DB = os.environ.get("ELGAKU_DB", os.path.join(ROOT, "elgaku.db"))
PORT = int(os.environ.get("PORT", "8000"))
HOST = "::"  # dual-stack: IPv6 + IPv4 (localhost:8000 va 127.0.0.1:8000 ishlaydi)
CHAT_RETENTION_DAYS = 40  # operatorlar chat xabarlari necha kun saqlanadi


# ==================== AI MURABBIY (ELGAKU) ====================
# Q&A baza ichga joylangan — alohida fayl talab qilmaydi.
_KB_JSON = r'''
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

try:
    _KB = json.loads(_KB_JSON)
except Exception:
    _KB = {"categories": []}

_QA_INDEX = []
for _cat in _KB.get("categories", []):
    for _it in _cat.get("qa", []):
        _kws = set()
        for _q in _it.get("q", []):
            for _w in re.findall(r"[a-z']+", _q.lower()):
                if len(_w) >= 3:
                    _kws.add(_w)
        _QA_INDEX.append({"kws": _kws, "answer": _it.get("a", "")})


def ai_reply(message):
    msg = set(w for w in re.findall(r"[a-z']+", (message or "").lower()) if len(w) >= 3)
    if not msg:
        return "Salom! 👋 Men sizning shaxsiy murabbiyingizman. 'Bugun nima qilay?' deb yozing."
    best_s, best_a = 0, None
    for e in _QA_INDEX:
        s = len(msg & e["kws"])
        if s > best_s:
            best_s, best_a = s, e["answer"]
    if best_a and best_s >= 1:
        return best_a
    return ("Tushundim! 🤔 Bu savolni hozircha topa olmadim. Lekin yordam bera olaman:\n\n"
            "- 'Bugun nima qilay?' — mashq tanlayman\n"
            "- 'Menga haftalik reja tuz' — to'liq jadval\n"
            "- 'Texnika maslahat' — yugurish uslubi\n"
            "- 'Motivatsiya kerak' — sizni ruhlantiraman 💪")
# ==================== AI MURABBIY TUGADI ====================


def get_db():
    db = sqlite3.connect(DB, timeout=20)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=15000")
    return db


def init_db():
    db = get_db()
    c = db.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS halls(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT, owner TEXT, status TEXT,
        phone TEXT, branch INTEGER DEFAULT 1,
        commission TEXT DEFAULT '—',
        login TEXT, created TEXT
    )""")
    # Eski sxemaga yangi ustunlar kerak bo'lsa — qo'shamiz
    existing = {r[1] for r in c.execute("PRAGMA table_info(halls)")}
    cols = {
        "phone": "TEXT",
        "branch": "INTEGER DEFAULT 1",
        "commission": "TEXT DEFAULT '—'",
        "login": "TEXT",
        "created": "TEXT",
        "type": "TEXT",
        "details": "TEXT",
        "pass": "TEXT DEFAULT ''",
    }
    for col, ddl in cols.items():
        if col not in existing:
            c.execute("ALTER TABLE halls ADD COLUMN %s %s" % (col, ddl))
    # Korporativ mijozlar (B2B wellness) jadvali
    c.execute("""CREATE TABLE IF NOT EXISTS corporate(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT, contact TEXT, phone TEXT, email TEXT,
        inn TEXT, status TEXT DEFAULT 'yangi',
        plan TEXT DEFAULT 'oylik',
        employees INTEGER DEFAULT 0,
        amount TEXT DEFAULT '—',
        start TEXT, end TEXT,
        created TEXT, details TEXT
    )""")
    # Tashriflar statistikasi (sayt + APK)
    c.execute("""CREATE TABLE IF NOT EXISTS visits(
        d TEXT PRIMARY KEY,
        sayt INTEGER DEFAULT 0,
        apk INTEGER DEFAULT 0
    )""")
    # APK foydalanuvchilari (operator panelidagi "APK Sayt foydalanuvchilari" bo'limi)
    c.execute("""CREATE TABLE IF NOT EXISTS apk_users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT UNIQUE,
        pass TEXT DEFAULT '',
        name TEXT DEFAULT '',
        created TEXT,
        last_login TEXT,
        status TEXT DEFAULT 'faol',
        source TEXT DEFAULT 'apk'
    )""")
    # Korporativ paketlar (operator tomonidan boshqariladi)
    c.execute("""CREATE TABLE IF NOT EXISTS corp_packages(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        seats INTEGER DEFAULT 0,
        price INTEGER DEFAULT 0,
        sort INTEGER DEFAULT 0
    )""")
    pc = c.execute("SELECT COUNT(*) FROM corp_packages").fetchone()[0]
    if pc == 0:
        c.executemany("INSERT INTO corp_packages(name, seats, price, sort, commission) VALUES(?,?,?,?,?)", [
            ("Standard 50", 50, 5000000, 1, 12),
            ("Elite 120", 120, 10800000, 2, 12),
            ("Custom", 0, 0, 3, 12),
        ])
    pex = {r[1] for r in c.execute("PRAGMA table_info(corp_packages)")}
    if "commission" not in pex:
        c.execute("ALTER TABLE corp_packages ADD COLUMN commission INTEGER DEFAULT 0")
        c.execute("UPDATE corp_packages SET commission=12 WHERE commission=0")
    # To'lovlar va checklar (ELGAKU nomidan QR kodli)
    c.execute("""CREATE TABLE IF NOT EXISTS corp_payments(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        corp_id INTEGER,
        receipt_no TEXT,
        amount TEXT,
        commission TEXT,
        method TEXT,
        pdate TEXT,
        status TEXT DEFAULT 'paid',
        operator TEXT,
        created TEXT,
        details TEXT
    )""")
    # Xodimlar (RBAC) — server-side, barcha brauzerlarda umumiy va saqlanadigan
    c.execute("""CREATE TABLE IF NOT EXISTS employees(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT, role TEXT, login TEXT, pass TEXT, status TEXT DEFAULT 'faol',
        perms TEXT DEFAULT '[]', brought INTEGER DEFAULT 0, deals INTEGER DEFAULT 0,
        conv TEXT DEFAULT '', photo TEXT DEFAULT '', note TEXT DEFAULT '',
        created TEXT, last_active TEXT
    )""")
    cnt = c.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
    if cnt == 0:
        now = time.strftime("%Y-%m-%d %H:%M")
        c.executemany("INSERT INTO employees(name, role, login, pass, status, perms, brought, deals, conv, note, created) VALUES(?,?,?,?,?,?,?,?,?,?,?)", [
            ("Fayziyev Aziz", "Operator", "user871", "elgaku2026", "faol", '["partners","payments","corporate"]', 5, 8, "62", "Surxondaryo", now),
            ("Sharipova Aziza", "Operator", "user744", "elgaku2026", "faol", "[]", 3, 5, "45", "Toshkent", now),
            ("Malika Bahromovna", "Operator", "Malika77", "elgaku2026", "faol", '["monitoring"]', 2, 3, "58", "Toshkent", now),
        ])
    db.execute("""CREATE TABLE IF NOT EXISTS settings(
        key TEXT PRIMARY KEY, value TEXT
    )""")
    for _k, _v in (("super_login","operator"),("super_pass","elgaku2026"),("super_name","Super Admin"),("super_photo","")):
        db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (_k, _v))
    db.execute("""CREATE TABLE IF NOT EXISTS tickets(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tid TEXT, source TEXT, type TEXT, author TEXT, contact TEXT,
        hall TEXT, subject TEXT, body TEXT, priority TEXT DEFAULT 'normal',
        status TEXT DEFAULT 'yangi', assignee TEXT DEFAULT '',
        history TEXT DEFAULT '[]', chat TEXT DEFAULT '[]', followup TEXT DEFAULT '', created TEXT, updated TEXT
    )""")
    for _col in ("chat", "followup"):
        try:
            db.execute("ALTER TABLE tickets ADD COLUMN %s TEXT DEFAULT '[]'" % _col)
        except Exception:
            pass

    # --- Dars bronlari (牛啦/微健 uslubi): guruh darsi + shaxsiy dars + navbat (waitlist) ---
    # Eski "bookings" jadvali boshqa sxemada (zal/joy bronlari) mavjud — shuning uchun yangi nom: lesson_bookings
    db.execute("""CREATE TABLE IF NOT EXISTS lesson_bookings(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hall TEXT DEFAULT '', lesson_id INTEGER DEFAULT 0,
        client TEXT DEFAULT '', phone TEXT DEFAULT '', seats INTEGER DEFAULT 1,
        status TEXT DEFAULT 'bron',   -- bron / kelgan / kelmadi / bekor / navbat
        note TEXT DEFAULT '', created TEXT DEFAULT ''
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS hall_settings(
        hall TEXT DEFAULT '', k TEXT DEFAULT '', v TEXT DEFAULT ''
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS staff(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hall TEXT DEFAULT '', name TEXT DEFAULT '', role TEXT DEFAULT 'trener',
        base_salary INTEGER DEFAULT 0, per_lesson INTEGER DEFAULT 0,
        sales_percent INTEGER DEFAULT 0, active TEXT DEFAULT '1', created TEXT DEFAULT ''
    )""")
    # Eski "coupons" jadvali boshqa sxemada mavjud — yangi nom: promo_coupons
    db.execute("""CREATE TABLE IF NOT EXISTS promo_coupons(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hall TEXT DEFAULT '', code TEXT DEFAULT '', title TEXT DEFAULT '',
        kind TEXT DEFAULT 'chegirma',   -- chegirma / bepul / taklif
        amount INTEGER DEFAULT 0, percent INTEGER DEFAULT 0,
        active TEXT DEFAULT '1', used INTEGER DEFAULT 0, created TEXT DEFAULT ''
    )""")
    # Tana o'lchovi tarixi (vazn / BMI / yog' foizi) — vaqt o'tishi bilan grafik (牛啦 uslubi)
    db.execute("""CREATE TABLE IF NOT EXISTS body_measurements(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hall TEXT DEFAULT '', client TEXT DEFAULT '', phone TEXT DEFAULT '',
        weight REAL DEFAULT 0, bmi REAL DEFAULT 0, fat REAL DEFAULT 0,
        note TEXT DEFAULT '', created TEXT DEFAULT ''
    )""")
    tc = db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
    if tc == 0:
        now = time.strftime("%Y-%m-%d %H:%M")
        db.executemany("INSERT INTO tickets(tid,source,type,author,contact,hall,subject,body,priority,status,assignee,history,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [
            ("T-1001","zal","texnik","FIT-PRO egasi","+998909991122","FIT-PRO","Kirish uskunasi ishlamayapti","Turniket panelga ulanmayapti, yordam bering.","yuqori","yangi","","[]",now,now),
            ("T-1002","zal","savol","Navro'z KTV egasi","+998909992233","Navro'z KTV","Komissiya foizi","Komissiyamiz necha foiz ekanini tasdiqlang.","normal","jarayonda","Sharipova Aziza",'[{"t":"%s","who":"Tizim","note":"Operatorga tayinlandi"},{"t":"%s","who":"Sharipova Aziza","note":"Komissiya tekshirilmoqda"}]'%(now,now),now,now),
            ("T-1003","operator","taklif","Sharipova Aziza","","Saye Fit","Yangilangan dizayn","Panel yangi dizaynida abonement bo'limi sinovdan o'tdi.","past","hal","Sharipova Aziza",'[{"t":"%s","who":"Tizim","note":"Operatorga tayinlandi"},{"t":"%s","who":"Sharipova Aziza","note":"Saye Fit egasi tasdiqladi"}]'%(now,now),now,now),
        ])
    db.execute("""CREATE TABLE IF NOT EXISTS sms_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT, subject TEXT, text TEXT, status TEXT,
        operator TEXT, created TEXT
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS tasks(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT DEFAULT '',
        text TEXT DEFAULT '',
        deadline TEXT DEFAULT '',
        priority TEXT DEFAULT 'orta',
        files TEXT DEFAULT '[]',
        status TEXT DEFAULT 'yangi',
        assigned TEXT DEFAULT '[]',
        created_by TEXT DEFAULT '',
        created TEXT DEFAULT '',
        done_note TEXT DEFAULT '',
        done_files TEXT DEFAULT '[]',
        done_at TEXT DEFAULT ''
    )""")
    tx = {r[1] for r in db.execute("PRAGMA table_info(tasks)")}
    for _c, _d in (("photo_required", "INTEGER DEFAULT 0"), ("plan_date", "TEXT DEFAULT ''"), ("archived", "INTEGER DEFAULT 0")):
        if _c not in tx:
            try:
                db.execute("ALTER TABLE tasks ADD COLUMN %s %s" % (_c, _d))
            except Exception:
                pass
    tx2 = {r[1] for r in db.execute("PRAGMA table_info(tasks)")}
    for _c2, _d2 in (("category", "TEXT DEFAULT ''"), ("reminded", "INTEGER DEFAULT 0")):
        if _c2 not in tx2:
            try:
                db.execute("ALTER TABLE tasks ADD COLUMN %s %s" % (_c2, _d2))
            except Exception:
                pass
    ax = {r[1] for r in db.execute("PRAGMA table_info(attendance)")}
    if "suspicious" not in ax:
        try:
            db.execute("ALTER TABLE attendance ADD COLUMN suspicious INTEGER DEFAULT 0")
        except Exception:
            pass
    if "photo" not in ax:
        try:
            db.execute("ALTER TABLE attendance ADD COLUMN photo TEXT DEFAULT ''")
        except Exception:
            pass
    cx2 = {r[1] for r in db.execute("PRAGMA table_info(chat_messages)")}
    if "target" not in cx2:
        try:
            db.execute("ALTER TABLE chat_messages ADD COLUMN target TEXT DEFAULT ''")
        except Exception:
            pass
    db.execute("""CREATE TABLE IF NOT EXISTS attendance(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        emp TEXT DEFAULT '', emp_name TEXT DEFAULT '', date TEXT DEFAULT '',
        checkin TEXT DEFAULT '', checkout TEXT DEFAULT '',
        lat REAL DEFAULT 0, lon REAL DEFAULT 0, dist REAL DEFAULT 0,
        created TEXT DEFAULT ''
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS daily_reports(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        emp TEXT DEFAULT '',
        emp_name TEXT DEFAULT '',
        work TEXT DEFAULT '',
        period TEXT DEFAULT '',
        note TEXT DEFAULT '',
        files TEXT DEFAULT '[]',
        created TEXT DEFAULT ''
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS login_attempts(
        device TEXT PRIMARY KEY, count INTEGER DEFAULT 0,
        blocked_until TEXT DEFAULT '', updated TEXT DEFAULT ''
    )""")
    try:
        os.makedirs(os.path.join(ROOT, "uploads", "tasks"), exist_ok=True)
    except Exception:
        pass
    db.execute("""CREATE TABLE IF NOT EXISTS chat_messages(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender TEXT, text TEXT, created TEXT,
        dur INTEGER DEFAULT 0
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS idx_chat_created ON chat_messages(created)")
    cx = {r[1] for r in db.execute("PRAGMA table_info(chat_messages)")}
    if "img" not in cx:
        db.execute("ALTER TABLE chat_messages ADD COLUMN img TEXT DEFAULT ''")
    if "fname" not in cx:
        db.execute("ALTER TABLE chat_messages ADD COLUMN fname TEXT DEFAULT ''")
    if "edited" not in cx:
        db.execute("ALTER TABLE chat_messages ADD COLUMN edited INTEGER DEFAULT 0")
    if "sticker" not in cx:
        db.execute("ALTER TABLE chat_messages ADD COLUMN sticker TEXT DEFAULT ''")
    if "reply_to" not in cx:
        db.execute("ALTER TABLE chat_messages ADD COLUMN reply_to INTEGER DEFAULT 0")
    if "dur" not in cx:
        db.execute("ALTER TABLE chat_messages ADD COLUMN dur INTEGER DEFAULT 0")
    db.execute("""CREATE TABLE IF NOT EXISTS chat_online(
        login TEXT PRIMARY KEY, name TEXT, last_seen INTEGER
    )""")
    # ---------- Zal egasi paneli uchun jadvallar ----------
    db.execute("""CREATE TABLE IF NOT EXISTS hall_visits(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hall TEXT DEFAULT '', person TEXT DEFAULT '', phone TEXT DEFAULT '',
        kind TEXT DEFAULT 'mijoz', status TEXT DEFAULT 'kirgan',
        note TEXT DEFAULT '', created TEXT DEFAULT ''
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS bookings(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hall TEXT DEFAULT '', item TEXT DEFAULT '',
        cdate TEXT DEFAULT '', start TEXT DEFAULT '', end TEXT DEFAULT '',
        client TEXT DEFAULT '', phone TEXT DEFAULT '',
        status TEXT DEFAULT 'yangi', note TEXT DEFAULT '', created TEXT DEFAULT ''
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS coupons(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hall TEXT DEFAULT '', code TEXT DEFAULT '', title TEXT DEFAULT '',
        type TEXT DEFAULT 'percent', value TEXT DEFAULT '10',
        qty INTEGER DEFAULT 0, used INTEGER DEFAULT 0,
        valid_from TEXT DEFAULT '', valid_to TEXT DEFAULT '',
        active INTEGER DEFAULT 1, created TEXT DEFAULT ''
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS announcements(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hall TEXT DEFAULT '', title TEXT DEFAULT '', body TEXT DEFAULT '', created TEXT DEFAULT ''
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS coach_schedule(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hall TEXT DEFAULT '', coach TEXT DEFAULT '', title TEXT DEFAULT '',
        kind TEXT DEFAULT 'guruh', cdate TEXT DEFAULT '', ctime TEXT DEFAULT '',
        seats INTEGER DEFAULT 0, booked INTEGER DEFAULT 0,
        price TEXT DEFAULT '', created TEXT DEFAULT ''
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS withdrawals(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hall TEXT DEFAULT '', amount TEXT DEFAULT '', status TEXT DEFAULT 'kutilmoqda',
        created TEXT DEFAULT '', note TEXT DEFAULT ''
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS hall_payments(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hall TEXT DEFAULT '', client TEXT DEFAULT '', phone TEXT DEFAULT '',
        amount TEXT DEFAULT '0', method TEXT DEFAULT 'Naqd',
        kind TEXT DEFAULT 'obuna', note TEXT DEFAULT '',
        status TEXT DEFAULT 'paid', created TEXT DEFAULT ''
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS vending_products(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hall TEXT DEFAULT '', name TEXT DEFAULT '', price TEXT DEFAULT '0',
        stock INTEGER DEFAULT 0, low_stock INTEGER DEFAULT 3,
        active INTEGER DEFAULT 1, created TEXT DEFAULT ''
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS vending_orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hall TEXT DEFAULT '', product TEXT DEFAULT '', qty INTEGER DEFAULT 1,
        amount TEXT DEFAULT '0', created TEXT DEFAULT ''
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS packages(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hall TEXT DEFAULT '', title TEXT DEFAULT '', desc TEXT DEFAULT '',
        price TEXT DEFAULT '0', old_price TEXT DEFAULT '',
        qty INTEGER DEFAULT 0, sold INTEGER DEFAULT 0,
        active INTEGER DEFAULT 1, created TEXT DEFAULT ''
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS hall_reviews(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hall TEXT DEFAULT '', author TEXT DEFAULT '', rating INTEGER DEFAULT 5,
        text TEXT DEFAULT '', reply TEXT DEFAULT '', created TEXT DEFAULT ''
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS memberships(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hall TEXT DEFAULT '', client TEXT DEFAULT '', phone TEXT DEFAULT '',
        type TEXT DEFAULT 'muddatli', sessions_total INTEGER DEFAULT 0,
        sessions_used INTEGER DEFAULT 0, price TEXT DEFAULT '0',
        start TEXT DEFAULT '', end TEXT DEFAULT '',
        status TEXT DEFAULT 'faol', created TEXT DEFAULT ''
    )""")
    # Yangi maydonlar (eski bazalar uchun xavfsiz migratsiya)
    for _col, _sql in (
        ("packages.months", "ALTER TABLE packages ADD COLUMN months INTEGER DEFAULT 1"),
        ("memberships.photo", "ALTER TABLE memberships ADD COLUMN photo TEXT DEFAULT ''"),
        ("memberships.passport", "ALTER TABLE memberships ADD COLUMN passport TEXT DEFAULT ''"),
        ("memberships.package", "ALTER TABLE memberships ADD COLUMN package TEXT DEFAULT ''"),
        ("memberships.contract_end", "ALTER TABLE memberships ADD COLUMN contract_end TEXT DEFAULT ''"),
    ):
        try:
            db.execute(_sql)
        except Exception:
            pass
    # Qo'lda kiritilgan mijozlar (zal egasi tomonidan): tasdiqlash holati bilan
    db.execute("""CREATE TABLE IF NOT EXISTS clients(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hall TEXT DEFAULT '', person TEXT DEFAULT '', phone TEXT DEFAULT '',
        status TEXT DEFAULT 'yangi',  -- yangi / tasdiqlangan / blok
        note TEXT DEFAULT '', created TEXT DEFAULT ''
    )""")
    # Mijoz kartotekasi: yorliqlar (teglar) va tana o'lchovi (vazn) — 微健 uslubi
    for _col, _sql in (
        ("clients.tag", "ALTER TABLE clients ADD COLUMN tag TEXT DEFAULT ''"),
        ("clients.weight", "ALTER TABLE clients ADD COLUMN weight TEXT DEFAULT ''"),
    ):
        try:
            db.execute(_sql)
        except Exception:
            pass
    # Eski abonementlarga ham 1 yillik shartnoma tugash sanasini to'ldiramiz
    try:
        db.execute("UPDATE memberships SET contract_end = date(start, '+365 days') WHERE contract_end='' AND start != ''")
    except Exception:
        pass
    # Kassa (pul oldi-berdi nazorati): kirim / chiqim / smena yopish — har yozuv audit bilan
    db.execute("""CREATE TABLE IF NOT EXISTS cashbox(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        hall TEXT DEFAULT '', direction TEXT DEFAULT 'kirim',
        amount REAL DEFAULT 0, method TEXT DEFAULT 'Naqd',
        note TEXT DEFAULT '', actor TEXT DEFAULT '',
        created TEXT DEFAULT ''
    )""")
    # Xavfsizlik: audit jurnali (barcha muhim operator/egasi harakatlari)
    db.execute("""CREATE TABLE IF NOT EXISTS audit_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        actor TEXT DEFAULT '', role TEXT DEFAULT '',
        action TEXT DEFAULT '', target TEXT DEFAULT '',
        detail TEXT DEFAULT '', created TEXT DEFAULT ''
    )""")
    # Demo sharhlar — zalda sharh bo'lmasa (turli xil reyting/son, mashhurlik saralashi uchun)
    try:
        demo_trio = ("Diyor", "Madina", "Sardor")
        texts = ["Juda chiroyli joy, xonalar toza, xizmat tez. Yana kelamiz!",
                 "Umuman yaxshi, lekin dam olish kunlari band bo'ladi. Oldindan bron qiling.",
                 "O'rtacha. Ovoz tizimini yangilash zarar qilmaydi.",
                 "Zo'r muhit, narxlar ham maqul. Do'stlarimga tavsiya qildim.",
                 "Birinchi marta keldim, juda yoqdi. Yana albatta kelaman!",
                 "Xodimlar samimiy, joy toza va qulay."]
        halls = db.execute("SELECT name FROM halls WHERE name IS NOT NULL AND name != ''").fetchall()
        for h in halls:
            rows = db.execute("SELECT author FROM hall_reviews WHERE hall=?", (h["name"],)).fetchall()
            is_demo_trio = (len(rows) == 3 and all(r["author"] in demo_trio for r in rows))
            if not rows or is_demo_trio:
                if is_demo_trio:
                    db.execute("DELETE FROM hall_reviews WHERE hall=?", (h["name"],))
                n = random.randint(2, 10)
                now = time.strftime("%Y-%m-%d %H:%M")
                for i in range(n):
                    rnd = random.random()
                    rating = 5 if rnd < 0.5 else (4 if rnd < 0.8 else 3)
                    db.execute("INSERT INTO hall_reviews(hall,author,rating,text,reply,created) VALUES(?,?,?,?,?,?)",
                               (h["name"], "Foydalanuvchi " + str(i + 1), rating,
                                random.choice(texts), "", now))
    except Exception:
        pass
    db.commit()
    db.close()


def get_setting(key, default=""):
    db = get_db()
    r = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    db.close()
    return r["value"] if r else default


def set_setting(key, value):
    db = get_db()
    db.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))
    db.commit()
    db.close()


# ---------- Xavfsizlik: audit jurnali va zaxira ----------
def audit(actor, role, action, target="", detail=""):
    """Har qanday muhim harakatni xavfsizlik jurnaliga yozadi (hech qachon bajarilmay qolmasligi uchun try/except)."""
    try:
        db = get_db()
        db.execute("INSERT INTO audit_log(actor,role,action,target,detail,created) VALUES(?,?,?,?,?,?)",
                   (actor or "", role or "", action or "", target or "", detail or "",
                    time.strftime("%Y-%m-%d %H:%M:%S")))
        db.commit()
        db.close()
    except Exception:
        pass


BACKUP_DIR = os.path.join(ROOT, "backups")


def backup_db():
    """elgaku.db ning zaxira nusxasini backups/ papkasiga yaratadi (oxirgi 14 ta saqlanadi)."""
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        src = os.path.join(ROOT, "elgaku.db")
        if not os.path.isfile(src):
            return ""
        name = "elgaku_" + time.strftime("%Y-%m-%d_%H%M") + ".db"
        dst = os.path.join(BACKUP_DIR, name)
        import shutil
        shutil.copy2(src, dst)
        # eski zaxiralarni tozalash (14 tadan ko'p bo'lsa)
        files = sorted(f for f in os.listdir(BACKUP_DIR) if f.startswith("elgaku_") and f.endswith(".db"))
        for f in files[:-14]:
            try:
                os.remove(os.path.join(BACKUP_DIR, f))
            except Exception:
                pass
        return name
    except Exception:
        return ""


def haversine_m(lat1, lon1, lat2, lon2):
    import math
    R = 6371000.0
    p1 = math.radians(lat1); p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1); dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _task_dict(r, names=None):
    d = {
        "id": r["id"], "title": r["title"], "text": r["text"],
        "deadline": r["deadline"], "priority": r["priority"] or "orta",
        "files": json.loads(r["files"] or "[]"), "status": r["status"] or "yangi",
        "assigned": json.loads(r["assigned"] or "[]"),
        "created_by": r["created_by"], "created": r["created"],
        "done_note": r["done_note"] or "", "done_files": json.loads(r["done_files"] or "[]"),
        "done_at": r["done_at"] or "",
        "photo_required": r["photo_required"] if "photo_required" in r.keys() else 0,
        "plan_date": r["plan_date"] if "plan_date" in r.keys() else "",
        "archived": r["archived"] if "archived" in r.keys() else 0,
        "category": r["category"] if "category" in r.keys() else "",
        "reminded": r["reminded"] if "reminded" in r.keys() else 0
    }
    cb = str(r["created_by"] or "")
    if names is not None:
        d["created_by_name"] = names.get(cb.lower()) or (cb if cb else "")
    else:
        d["created_by_name"] = cb
    return d


def _chat_card_task(db, t, emp_login):
    now = time.strftime("%Y-%m-%d %H:%M")
    payload = json.dumps({"type": "task", "id": t["id"], "title": t["title"],
                          "text": (t["text"] or "")[:200], "deadline": t["deadline"] or "",
                          "priority": t["priority"] or "orta", "photo": t["photo_required"] or 0}, ensure_ascii=False)
    db.execute("INSERT INTO chat_messages(sender,text,target,created) VALUES(?,?,?,?)",
               ("📋 Topshiriq", payload, emp_login, now))


def _promote_tasks(db):
    today = datetime.date.today().isoformat()
    rows = db.execute("SELECT * FROM tasks WHERE status='reja' AND plan_date!='' AND plan_date<=?", (today,)).fetchall()
    for r in rows:
        t = _task_dict(r)
        db.execute("UPDATE tasks SET status='yangi' WHERE id=?", (t["id"],))
        for lg in t["assigned"]:
            _chat_card_task(db, t, lg)
    db.commit()


def _archive_tasks(db):
    cut = (datetime.date.today() - datetime.timedelta(days=10)).isoformat()
    db.execute("UPDATE tasks SET archived=1 WHERE archived=0 AND status IN ('bajarildi','rad') AND done_at!='' AND substr(done_at,1,10)<=?", (cut,))
    db.commit()


def _remind_tasks(db):
    """Muddati 24 soat ichida (yoki o'tgan) va hali eslatilmagan topshiriqlar uchun chat eslatmasi yuboriladi."""
    now = datetime.datetime.now()
    now24 = now + datetime.timedelta(hours=24)
    rows = db.execute("SELECT * FROM tasks WHERE archived=0 AND status NOT IN ('bajarildi','rad','reja') AND deadline!='' AND reminded=0").fetchall()
    rceo = db.execute("SELECT value FROM settings WHERE key='super_login'").fetchone()
    ceo = rceo["value"] if rceo else "operator"
    for r in rows:
        t = _task_dict(r)
        try:
            dl = datetime.datetime.strptime(t["deadline"], "%Y-%m-%d")
        except Exception:
            try:
                dl = datetime.datetime.strptime(t["deadline"], "%Y-%m-%d %H:%M")
            except Exception:
                continue
        if dl <= now24:
            late = 1 if dl < now else 0
            payload = json.dumps({"type": "remind", "id": t["id"], "title": t["title"],
                                  "deadline": t["deadline"], "late": late}, ensure_ascii=False)
            nw = time.strftime("%Y-%m-%d %H:%M")
            for lg in t["assigned"]:
                db.execute("INSERT INTO chat_messages(sender,text,target,created) VALUES(?,?,?,?)",
                           ("⏰ Eslatma", payload, lg, nw))
            if ceo:
                db.execute("INSERT INTO chat_messages(sender,text,target,created) VALUES(?,?,?,?)",
                           ("⏰ Eslatma", payload, ceo, nw))
            db.execute("UPDATE tasks SET reminded=1 WHERE id=?", (t["id"],))
    db.commit()


def _weekly_report(db):
    """Haftalik avto-jamlama: kunlik hisobotlardan CEOga chat orqali (haftada 1 marta)."""
    today = datetime.date.today()
    rlast = db.execute("SELECT value FROM settings WHERE key='last_weekly'").fetchone()
    last = rlast["value"] if rlast else ""
    if last:
        try:
            ld = datetime.date.fromisoformat(last[:10])
            if (today - ld).days < 7:
                return
        except Exception:
            pass
    week_ago = today - datetime.timedelta(days=7)
    rows = db.execute("SELECT emp,emp_name,work,created FROM daily_reports WHERE created>=? ORDER BY emp_name",
                      (week_ago.strftime("%Y-%m-%d %H:%M"),)).fetchall()
    done = db.execute("SELECT COUNT(*) c FROM tasks WHERE status='bajarildi' AND done_at>=?",
                      (week_ago.strftime("%Y-%m-%d %H:%M"),)).fetchone()["c"]
    by = {}
    for r in rows:
        k = r["emp_name"] or r["emp"]
        by.setdefault(k, []).append(r)
    lines = []
    for k in sorted(by):
        recs = by[k]
        first = (recs[0]["work"] or "").replace("\n", " ")[:60]
        lines.append("• %s: %d ta yozuv — %s" % (k, len(recs), first))
    if not lines:
        lines.append("• Hech qanday yozuv yo'q")
    text = "📊 Haftalik jamlama (%s — %s)\n%s\n✅ Bajarilgan topshiriqlar: %d" % (
        week_ago.strftime("%d.%m"), (today - datetime.timedelta(days=1)).strftime("%d.%m"),
        "\n".join(lines), done)
    rceo = db.execute("SELECT value FROM settings WHERE key='super_login'").fetchone()
    ceo = rceo["value"] if rceo else "operator"
    db.execute("INSERT INTO chat_messages(sender,text,target,created) VALUES(?,?,?,?)",
               ("📊 Haftalik hisobot", text, ceo, time.strftime("%Y-%m-%d %H:%M")))
    db.execute("INSERT INTO settings(key,value) VALUES('last_weekly',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (today.isoformat(),))
    db.commit()


def _xlsx(headers, rows, red_flags=None):
    import zipfile, io as _io
    def esc(v):
        return str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&#39;")
    def cell(v, red=False):
        if v is None: v = ""
        if isinstance(v, (int, float)):
            return ('<c s="1" t="n"><v>%s</v></c>' % v) if red else ('<c t="n"><v>%s</v></c>' % v)
        return ('<c s="1" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % esc(v)) if red else ('<c t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % esc(v))
    def rowxml(r, flags=None):
        return "<row>%s</row>" % "".join(cell(x, bool(flags and flags[j])) for j, x in enumerate(r))
    rf = red_flags or []
    sheet = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>%s%s</sheetData></worksheet>' % (
        rowxml(headers), "".join(rowxml(r, rf[i] if i < len(rf) else None) for i, r in enumerate(rows)))
    ct = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>'
    rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'
    wb = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Davomat" sheetId="1" r:id="rId1"/></sheets></workbook>'
    wbrels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>'
    styles = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFFFC7CE"/></patternFill></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="0" fillId="1" borderId="0" xfId="0" applyFill="1"/></cellXfs></styleSheet>'
    buf = _io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rels)
        z.writestr("xl/workbook.xml", wb)
        z.writestr("xl/_rels/workbook.xml.rels", wbrels)
        z.writestr("xl/worksheets/sheet1.xml", sheet)
        z.writestr("xl/styles.xml", styles)
    return buf.getvalue()


def send_telegram(text):
    """Telegram integratsiyasi: settings (tg_token/tg_chat) yoki muhit o'zgaruvchilari."""
    tok = get_setting("tg_token", os.environ.get("ELGAKU_TG_TOKEN", ""))
    chat = get_setting("tg_chat", os.environ.get("ELGAKU_TG_CHAT", ""))
    if not tok or not chat:
        return False
    try:
        import urllib.request as _ur
        import urllib.parse as _up
        url = "https://api.telegram.org/bot%s/sendMessage" % tok
        data = _up.urlencode({"chat_id": chat, "text": text}).encode("utf-8")
        _ur.urlopen(url, data=data, timeout=6).read()
        return True
    except Exception:
        return False


def norm_phone(p):
    """O'zbekiston telefon raqamini +998XXXXXXXXX formatiga keltiradi; noto'g'ri bo'lsa None."""
    if not p:
        return None
    d = "".join(ch for ch in str(p) if ch.isdigit())
    if len(d) == 9:
        d = "998" + d
    if len(d) == 12 and d.startswith("998"):
        return "+" + d
    return None


def sms_recipients():
    """Barcha ro'yxatdan o'tgan foydalanuvchilar telefon raqamlari (zallar + korporativ), takrorlanmas."""
    db = get_db()
    nums = set()
    for r in db.execute("SELECT phone FROM corporate WHERE phone IS NOT NULL").fetchall():
        n = norm_phone(r["phone"])
        if n:
            nums.add(n)
    for r in db.execute("SELECT phone FROM halls WHERE phone IS NOT NULL AND phone != '—'").fetchall():
        n = norm_phone(r["phone"])
        if n:
            nums.add(n)
    db.close()
    return sorted(nums)


def cleanup_expired_contracts():
    """1 yillik shartnoma muddati o'tgan mijozlarning shaxsiy ma'lumotlarini o'chiradi:
    abonement, rasm/passport, kirish-chiqish jurnali, qo'lda mijoz yozuvi.
    Moliyaviy yozuvlar (to'lovlar) buxgalteriya uchun saqlanadi."""
    try:
        db = get_db()
        today = datetime.date.today().isoformat()
        rows = db.execute(
            "SELECT id, hall, client, phone FROM memberships WHERE contract_end != '' AND contract_end < ?",
            (today,)).fetchall()
        for m in rows:
            db.execute("DELETE FROM memberships WHERE id=?", (m["id"],))
            ph = (m["phone"] or "").strip()
            # Kirish-chiqish jurnali (hall_visits: person/phone)
            try:
                if ph:
                    db.execute("DELETE FROM hall_visits WHERE hall=? AND phone=?", (m["hall"], ph))
                else:
                    db.execute("DELETE FROM hall_visits WHERE hall=? AND person=?", (m["hall"], m["client"]))
            except Exception:
                pass
            # Qo'lda mijoz yozuvi (clients: person/phone)
            try:
                if ph:
                    db.execute("DELETE FROM clients WHERE hall=? AND phone=?", (m["hall"], ph))
                else:
                    db.execute("DELETE FROM clients WHERE hall=? AND person=?", (m["hall"], m["client"]))
            except Exception:
                pass
        if rows:
            db.commit()
            print("Shartnoma muddati o'tgan ma'lumotlar o'chirildi: %d ta mijoz" % len(rows))
        db.close()
    except Exception as e:
        try:
            db.close()
        except Exception:
            pass
        print("cleanup_expired_contracts xatosi:", e)


def track_visit(path, ua):
    """Sayt/APK tashriflarini kun bo'yicha hisoblaydi (get_db row factory bilan)."""
    ua = (ua or "")
    is_page = path in ("/", "/index.html") or path.endswith(".html")
    is_apk_ua = any(k in ua for k in ("ELGAKU-APK", "okhttp", "Dart/", "dart:", "Flutter"))
    if path.startswith("/api/"):
        if not is_apk_ua:
            return
        src = "apk"
    elif is_page:
        src = "sayt"
    else:
        return
    d = datetime.date.today().isoformat()
    db = get_db()
    db.execute("INSERT OR IGNORE INTO visits(d, sayt, apk) VALUES(?,0,0)", (d,))
    db.execute("UPDATE visits SET %s = %s + 1 WHERE d = ?" % (src, src), (d,))
    db.commit()
    db.close()


def send_sms(phone, text):
    """SMS yuborish.
    ELGAKU_SMS_URL (va ixtiyoriy ELGAKU_SMS_LOGIN / ELGAKU_SMS_PASS) muhit o'zgaruvchilari
    berilsa — real SMS-provayderga POST qilinadi (JSON: {phone, text}, Basic auth).
    Berilmasa — log rejimi: xabar sms_log jadvaliga 'log' holatida yoziladi.
    Qaytaradi: 'sent' | 'log' | 'error'"""
    url = os.environ.get("ELGAKU_SMS_URL", "").strip()
    if not url:
        return "log"
    try:
        import urllib.request as _ur
        import base64 as _b64
        payload = json.dumps({"phone": phone, "text": text}, ensure_ascii=False).encode("utf-8")
        req = _ur.Request(url, data=payload, headers={"Content-Type": "application/json"})
        login = os.environ.get("ELGAKU_SMS_LOGIN", "").strip()
        if login:
            cred = (login + ":" + (os.environ.get("ELGAKU_SMS_PASS", "") or "")).encode("utf-8")
            req.add_header("Authorization", "Basic " + _b64.b64encode(cred).decode("ascii"))
        _ur.urlopen(req, timeout=10).read()
        return "sent"
    except Exception:
        return "error"


_last_chat_cleanup = [0.0]


def chat_cleanup():
    """CHAT_RETENTION_DAYS kunlik saqlash: eski xabarlarni o'chiradi.
    Xavfsizlik: DB ziddiyatidan qochish uchun daqiqada bir marta, xato yutib yuboriladi."""
    global _last_chat_cleanup
    now = time.time()
    if now - _last_chat_cleanup[0] < 60:
        return
    _last_chat_cleanup[0] = now
    try:
        db = get_db()
        cutoff = (datetime.datetime.now() - datetime.timedelta(days=CHAT_RETENTION_DAYS)).strftime("%Y-%m-%d %H:%M")
        db.execute("DELETE FROM chat_messages WHERE created < ?", (cutoff,))
        db.commit()
        db.close()
    except Exception:
        try:
            db.close()
        except Exception:
            pass


def row_to_ticket(r):
    return {
        "tid": r["tid"], "source": r["source"], "type": r["type"],
        "author": r["author"], "contact": r["contact"], "hall": r["hall"],
        "subject": r["subject"], "body": r["body"], "priority": r["priority"],
        "status": r["status"], "assignee": r["assignee"],
        "history": json.loads(r["history"] or "[]"),
        "chat": json.loads(r["chat"] or "[]"),
        "followup": r["followup"] or "",
        "created": r["created"], "updated": r["updated"],
    }


def row_to_corp(r):
    details = {}
    try:
        raw = r["details"]
        if raw:
            details = json.loads(raw)
    except Exception:
        details = {}
    return {
        "id": r["id"],
        "name": r["name"] or "",
        "contact": r["contact"] or "—",
        "phone": r["phone"] or "—",
        "email": r["email"] or "—",
        "inn": r["inn"] or "—",
        "status": r["status"] or "yangi",
        "plan": r["plan"] or "oylik",
        "employees": r["employees"] if r["employees"] is not None else 0,
        "amount": r["amount"] or "—",
        "start": r["start"] or "",
        "end": r["end"] or "",
        "created": r["created"] or "",
        "details": details,
    }


def row_to_pkg(r):
    return {
        "id": r["id"],
        "name": r["name"] or "",
        "seats": r["seats"] if r["seats"] is not None else 0,
        "price": r["price"] if r["price"] is not None else 0,
        "sort": r["sort"] if r["sort"] is not None else 0,
        "commission": r["commission"] if r["commission"] is not None else 0,
    }


def row_to_hall(r):
    details = {}
    try:
        raw = r["details"]
        if raw:
            details = json.loads(raw)
    except Exception:
        details = {}
    return {
        "id": r["id"],
        "name": r["name"] or "",
        "owner": r["owner"] or "—",
        "status": r["status"] or "active",
        "phone": r["phone"] or "—",
        "branch": r["branch"] if r["branch"] is not None else 1,
        "commission": r["commission"] or "—",
        "login": r["login"] or "",
        "pass": r["pass"] or "",
        "created": r["created"] or "",
        "type": r["type"] or "boshqa",
        "details": details,
    }


def _light_details(details):
    """Owner'ga yuboriladigan details'dan og'ir fayllarni olib tashlaydi
    (sessionStorage kvotasi 5MB — 16MB'lik javob login'ni buzardi)."""
    if not isinstance(details, dict):
        return details
    for k in ("idPhotoFile", "licenseFile", "photosList", "contractFile"):
        details.pop(k, None)
    return details


def row_to_pay(r):
    details = {}
    try:
        raw = r["details"]
        if raw:
            details = json.loads(raw)
    except Exception:
        details = {}
    receipt_no = r["receipt_no"] or ""
    corp_name = ""
    if "corp_name" in r.keys():
        corp_name = r["corp_name"] or ""
    return {
        "id": r["id"],
        "corp_id": r["corp_id"],
        "corp_name": corp_name,
        "receipt_no": receipt_no,
        "amount": r["amount"] or "—",
        "commission": r["commission"] or "0",
        "method": r["method"] or "bank",
        "pdate": r["pdate"] or "",
        "status": r["status"] or "paid",
        "created": r["created"] or "",
        "operator": r["operator"] or "Operator",
        "details": details,
        "verifyUrl": ("/api/payments/verify/" + receipt_no) if receipt_no else "",
    }


def row_to_emp(r):
    perms = []
    try:
        perms = json.loads(r["perms"] or "[]")
    except Exception:
        perms = []
    return {
        "id": r["id"],
        "name": r["name"] or "",
        "role": r["role"] or "Boshqa",
        "login": r["login"] or "",
        "pass": r["pass"] or "",
        "status": r["status"] or "faol",
        "perms": perms,
        "brought": r["brought"] if r["brought"] is not None else 0,
        "deals": r["deals"] if r["deals"] is not None else 0,
        "conv": r["conv"] or "",
        "photo": r["photo"] or "",
        "note": r["note"] or "",
        "created": r["created"] or "",
        "last_active": r["last_active"] or "",
    }


CAPTCHAS = {}

def _new_captcha():
    import random, uuid, base64, io as _io, datetime as _dt
    chars = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz"
    code = "".join(random.choice(chars) for _ in range(4))
    token = uuid.uuid4().hex[:16]
    data_url = None
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageFilter
        W, H = 360, 120
        img = Image.new("RGB", (W, H), (246, 246, 250))
        d = ImageDraw.Draw(img)
        font = None
        for fp in (r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\calibrib.ttf",
                   r"C:\Windows\Fonts\segoeuib.ttf", r"C:\Windows\Fonts\arial.ttf"):
            try:
                font = ImageFont.truetype(fp, 54)
                break
            except Exception:
                continue
        for _ in range(7):
            d.line([(random.randint(0, W), random.randint(0, H)),
                    (random.randint(0, W), random.randint(0, H))],
                   fill=(random.randint(140, 225), random.randint(140, 225), random.randint(140, 225)),
                   width=random.randint(1, 3))
        for _ in range(70):
            d.point((random.randint(0, W), random.randint(0, H)),
                    fill=(random.randint(120, 235), random.randint(120, 235), random.randint(120, 235)))
        x = 26
        for ch in code:
            col = (random.randint(25, 115), random.randint(25, 115), random.randint(25, 115))
            d.text((x + random.randint(-3, 3), 16 + random.randint(-4, 4)), ch, font=font, fill=col)
            x += 82
        img = img.filter(ImageFilter.SMOOTH_MORE)
        buf = _io.BytesIO()
        img.save(buf, "PNG")
        data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        data_url = None
    if data_url is None:
        # PIL o'rnatilmagan bo'lsa — SVG fallback (hech qanday kutubxona talab qilmaydi).
        # Shu tufayli captcha har qanday Python muhitida ishlaydi (server.py uchun xavfsiz).
        try:
            W, H = 360, 120
            svg = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">' % (W, H, W, H)]
            svg.append('<rect width="%d" height="%d" fill="#F6F6FA" rx="14"/>' % (W, H))
            for _ in range(7):
                x1, y1, x2, y2 = random.randint(0, W), random.randint(0, H), random.randint(0, W), random.randint(0, H)
                svg.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="rgb(%d,%d,%d)" stroke-width="%d"/>'
                           % (x1, y1, x2, y2, random.randint(140, 225), random.randint(140, 225),
                              random.randint(140, 225), random.randint(1, 3)))
            for _ in range(70):
                svg.append('<circle cx="%d" cy="%d" r="1.3" fill="rgb(%d,%d,%d)"/>'
                           % (random.randint(0, W), random.randint(0, H),
                              random.randint(120, 235), random.randint(120, 235), random.randint(120, 235)))
            x = 22
            for ch in code:
                svg.append('<text x="%d" y="78" font-size="64" font-family="Arial, Helvetica, sans-serif" '
                           'font-weight="bold" fill="rgb(%d,%d,%d)" transform="rotate(%d %d 78)">%s</text>'
                           % (x, random.randint(25, 115), random.randint(25, 115), random.randint(25, 115),
                              random.randint(-8, 8), x, ch))
                x += 84
            svg.append('</svg>')
            b64 = base64.b64encode("".join(svg).encode("utf-8")).decode("ascii")
            data_url = "data:image/svg+xml;base64," + b64
        except Exception:
            data_url = None
    CAPTCHAS[token] = {"code": code.lower(), "exp": _dt.datetime.now() + _dt.timedelta(minutes=5)}
    if len(CAPTCHAS) > 400:
        now = _dt.datetime.now()
        for k in [k for k, v in CAPTCHAS.items() if v["exp"] < now]:
            CAPTCHAS.pop(k, None)
    return token, data_url

class Handler(BaseHTTPRequestHandler):
    server_version = "ELGAKU/1.0"
    # login.html'dagi super-admin (CEO) hisobi
    SUPER_LOGIN = "operator"

    # ---------- Auth yordamchilari ----------
    def super_settings(self):
        db = get_db()
        rows = {r["key"]: r["value"] for r in db.execute("SELECT key,value FROM settings").fetchall()}
        db.close()
        return {
            "login": rows.get("super_login") or "operator",
            "pass": rows.get("super_pass") or "elgaku2026",
            "name": rows.get("super_name") or "Super Admin",
            "photo": rows.get("super_photo") or "",
        }

    def current_user(self):
        """X-Elgaku-Login header orqali joriy foydalanuvchini aniqlaydi."""
        lg = (self.headers.get("X-Elgaku-Login") or "").strip()
        if not lg:
            return None
        s = self.super_settings()
        if lg.lower() == (s["login"] or "operator").lower():
            return {"name": s["name"] or "Super Admin", "role": "CEO", "login": s["login"] or "operator", "super": True, "photo": s["photo"] or ""}
        db = get_db()
        row = db.execute("SELECT * FROM employees WHERE lower(login)=lower(?)", (lg,)).fetchone()
        db.close()
        if not row:
            return None
        emp = row_to_emp(row)
        emp["super"] = False
        return emp

    def is_ceo(self, u=None):
        u = u or self.current_user()
        return bool(u) and (u.get("super") or u.get("role") == "CEO")

    # ---------- API ----------
    def api(self, path):
        if path == "/api/visits" and self.command == "GET":
            db = get_db()
            rows = {r["d"]: r for r in db.execute("SELECT * FROM visits ORDER BY d").fetchall()}
            db.close()
            today = datetime.date.today()
            week = []
            for i in range(6, -1, -1):
                d = (today - datetime.timedelta(days=i)).isoformat()
                r = rows.get(d)
                week.append({"d": d, "sayt": r["sayt"] if r else 0, "apk": r["apk"] if r else 0})
            cur = rows.get(today.isoformat())
            ts = {"sayt": 0, "apk": 0}
            for r in rows.values():
                ts["sayt"] += r["sayt"]; ts["apk"] += r["apk"]
            return self.json(200, {
                "today": {"sayt": (cur["sayt"] if cur else 0), "apk": (cur["apk"] if cur else 0),
                          "total": (cur["sayt"] if cur else 0) + (cur["apk"] if cur else 0)},
                "week": week,
                "all": {"sayt": ts["sayt"], "apk": ts["apk"], "total": ts["sayt"] + ts["apk"]},
            })

        # ==================== APK: ro'yxatdan o'tish / kirish (jamoat API) ====================
        if path == "/api/apk/check" and self.command == "POST":
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                data = json.loads(raw.decode("utf-8"))
            except Exception:
                return self.json(400, {"error": "JSON noto'g'ri"})
            phone = norm_phone(data.get("phone"))
            if not phone:
                return self.json(400, {"error": "Telefon raqam noto'g'ri"})
            db = get_db()
            row = db.execute("SELECT id, phone, status FROM apk_users WHERE phone=?", (phone,)).fetchone()
            db.close()
            if row:
                return self.json(200, {"exists": True, "phone": phone,
                                       "message": "Siz allaqachon ro'yxatdan o'tgansiz"})
            return self.json(200, {"exists": False, "phone": phone,
                                   "message": "Yangi foydalanuvchi"})

        if path == "/api/apk/register" and self.command == "POST":
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                data = json.loads(raw.decode("utf-8"))
            except Exception:
                return self.json(400, {"error": "JSON noto'g'ri"})
            phone = norm_phone(data.get("phone"))
            pwd = (data.get("password") or "").strip()
            if not phone:
                return self.json(400, {"error": "Telefon raqam noto'g'ri"})
            if len(pwd) < 6:
                return self.json(400, {"error": "Parol kamida 6 belgi bo'lishi kerak"})
            db = get_db()
            existing = db.execute("SELECT id FROM apk_users WHERE phone=?", (phone,)).fetchone()
            if existing:
                db.close()
                return self.json(409, {"error": "Bu raqam allaqachon ro'yxatda", "already": True})
            now = time.strftime("%Y-%m-%d %H:%M")
            db.execute(
                "INSERT INTO apk_users(phone, pass, name, created, last_login, status, source) VALUES(?,?,?,?,?,?,?)",
                (phone, pwd, (data.get("name") or "").strip(), now, now, "faol", "apk")
            )
            db.commit()
            db.close()
            return self.json(200, {"ok": True, "phone": phone, "message": "Ro'yxatdan o'tdingiz"})

        if path == "/api/apk/login" and self.command == "POST":
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                data = json.loads(raw.decode("utf-8"))
            except Exception:
                return self.json(400, {"error": "JSON noto'g'ri"})
            phone = norm_phone(data.get("phone"))
            pwd = (data.get("password") or "").strip()
            if not phone:
                return self.json(400, {"error": "Telefon raqam noto'g'ri"})
            db = get_db()
            row = db.execute("SELECT id, phone, pass, status FROM apk_users WHERE phone=?", (phone,)).fetchone()
            if not row:
                db.close()
                return self.json(404, {"error": "Bu raqam ro'yxatda yo'q", "not_registered": True})
            if row["status"] != "faol":
                db.close()
                return self.json(403, {"error": "Hisob bloklangan"})
            if row["pass"] != pwd:
                db.close()
                return self.json(401, {"error": "Parol noto'g'ri"})
            db.execute("UPDATE apk_users SET last_login=? WHERE id=?",
                       (time.strftime("%Y-%m-%d %H:%M"), row["id"]))
            db.commit()
            db.close()
            return self.json(200, {"ok": True, "phone": phone, "message": "Xush kelibsiz"})

        # ── APK: musiqa ro'yxati (sport ekrani — musiqa bo'limi) ──
        # Serverdagi /music papkasidagi fayllarni o'zi topib ro'yxat beradi.
        # Yangi musiqa qo'shish: /music ichiga mp3/wav/m4a tashlash kifoya.
        if path == "/api/apk/music" and self.command == "GET":
            mdir = os.path.join(ROOT, "music")
            tracks = []
            try:
                for fn in sorted(os.listdir(mdir)):
                    if fn.lower().endswith((".mp3", ".wav", ".m4a", ".ogg", ".aac", ".flac")):
                        full = os.path.join(mdir, fn)
                        if os.path.isfile(full):
                            title = os.path.splitext(fn)[0].replace("_", " ")
                            tracks.append({
                                "id": fn,
                                "title": title,
                                "url": "/music/" + fn,
                                "size": os.path.getsize(full),
                            })
            except OSError:
                pass
            return self.json(200, tracks)

        # ── APK: musiqa yuklash (operator panelidan) ──
        if path == "/api/apk/music/upload" and self.command == "POST":
            u = self.current_user()
            if not (u and (u.get("super") or u.get("role") in ("CEO", "Operator"))):
                return self.json(403, {"error": "Faqat operator huquqi"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 50 * 1024 * 1024:
                    return self.json(400, {"error": "Fayl hajmi 0 dan 50MB gacha bo'lsin"})
                ctype = self.headers.get("Content-Type", "")
                fname = self.headers.get("X-Filename", "").strip()
                # xavfsiz fayl nomi
                import re as _re
                fname = _re.sub(r"[^A-Za-z0-9._-]", "_", fname)
                if not fname or "." not in fname:
                    fname = "track_%d.mp3" % int(time.time())
                ext = fname.rsplit(".", 1)[-1].lower()
                if ext not in ("mp3", "wav", "m4a", "ogg", "aac", "flac"):
                    return self.json(400, {"error": "Faqat audio fayllar (mp3/wav/m4a/...)"})
                mdir = os.path.join(ROOT, "music")
                os.makedirs(mdir, exist_ok=True)
                data = self.rfile.read(length)
                fpath = os.path.join(mdir, fname)
                with open(fpath, "wb") as f:
                    f.write(data)
                audit(u.get("login") or "?", u.get("role") or "Operator", "music_upload", fname,
                      "Operator musiqa yukladi: %s (%d bayt)" % (fname, len(data)))
                return self.json(200, {"ok": True, "filename": fname, "size": len(data)})
            except Exception as e:
                return self.json(500, {"error": str(e)})

        # ── APK: musiqani o'chirish ──
        if path.startswith("/api/apk/music/delete/") and self.command == "POST":
            u = self.current_user()
            if not (u and (u.get("super") or u.get("role") in ("CEO", "Operator"))):
                return self.json(403, {"error": "Faqat operator huquqi"})
            fn = path.rsplit("/", 1)[-1]
            import re as _re
            fn = _re.sub(r"[^A-Za-z0-9._-]", "", fn)
            fpath = os.path.join(ROOT, "music", fn)
            try:
                if os.path.isfile(fpath):
                    os.remove(fpath)
                    audit(u.get("login") or "?", u.get("role") or "Operator", "music_delete", fn,
                          "Operator musiqani o'chirdi: " + fn)
                    return self.json(200, {"ok": True})
                return self.json(404, {"error": "Fayl topilmadi"})
            except Exception as e:
                return self.json(500, {"error": str(e)})


        # ── AI murabbiy chat (APK Shaxsiy murabbiy ekrani) ──
        if path == "/api/ai/chat" and self.command == "POST":
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                data = json.loads(raw.decode("utf-8"))
            except Exception:
                return self.json(400, {"error": "JSON noto'g'ri"})
            msg = (data.get("message") or "").strip()
            if not msg:
                return self.json(200, {"reply": "Iltimos, savol yozing! 👋"})
            return self.json(200, {"reply": ai_reply(msg)})

        if path == "/api/apk/users" and self.command == "GET":
            u = self.current_user()
            if not (u and (u.get("super") or u.get("role") in ("CEO", "Operator"))):
                return self.json(403, {"error": "Kirish taqiqlangan"})
            db = get_db()
            rows = db.execute(
                "SELECT id, phone, name, created, last_login, status, source FROM apk_users ORDER BY id DESC"
            ).fetchall()
            db.close()
            return self.json(200, [dict(r) for r in rows])

        if path == "/api/stats/users" and self.command == "GET":
            db = get_db()
            def phones(sql, *a):
                out = set()
                for r in db.execute(sql, a).fetchall():
                    n = norm_phone(r[0])
                    if n:
                        out.add(n)
                return out
            sayt = phones("SELECT contact FROM tickets WHERE source='zal' OR source='operator' OR source='egasi'")
            apk = set()
            corp = phones("SELECT phone FROM corporate")
            halls = phones("SELECT phone FROM halls WHERE phone IS NOT NULL AND phone != '—'")
            db.close()
            allp = sayt | apk | corp | halls
            return self.json(200, {
                "sayt": len(sayt), "apk": len(apk),
                "corporate": len(corp), "halls": len(halls),
                "total": len(allp),
            })

        if path == "/api/halls" and self.command == "GET":
            db = get_db()
            rows = db.execute("SELECT * FROM halls ORDER BY id DESC").fetchall()
            rev = {}
            for rr in db.execute("SELECT hall, AVG(rating) a, COUNT(*) c FROM hall_reviews GROUP BY hall"):
                rev[rr["hall"]] = (round(rr["a"], 1), rr["c"])
            db.close()
            u = self.current_user()
            is_op = bool(u and (u.get("super") or u.get("role") in ("CEO", "Operator")))
            out = [row_to_hall(r) for r in rows]
            for h in out:
                rv = rev.get(h.get("name"))
                if rv:
                    h["rev_avg"] = rv[0]
                    h["rev_cnt"] = rv[1]
                else:
                    h["rev_avg"] = 0
                    h["rev_cnt"] = 0
            if not is_op:  # xavfsizlik: parol faqat operatorga ko'rinadi
                for h in out:
                    h.pop("pass", None)
            return self.json(200, out)

        # Jamoat API: zal tanlanganda sayt/APK "Obunalar" bo'limi uchun
        if path.startswith("/api/public/hall/") and self.command == "GET" and path.split("/")[-1].isdigit():
            try:
                hid = int(path.split("/")[-1])
            except ValueError:
                return self.json(400, {"error": "id noto'g'ri"})
            db = get_db()
            h = db.execute("SELECT * FROM halls WHERE id=? AND status='active'", (hid,)).fetchone()
            if not h:
                db.close()
                return self.json(404, {"error": "zal topilmadi"})
            hall = row_to_hall(h)
            hall.pop("pass", None)
            hname = hall["name"] or ""
            packages = [dict(r) for r in db.execute(
                "SELECT id,title,desc,price,old_price,qty,sold,months FROM packages WHERE hall=? AND active=1 ORDER BY id DESC", (hname,)).fetchall()]
            memberships = [dict(r) for r in db.execute(
                "SELECT id,client,type,sessions_total,sessions_used,price,start,end,status FROM memberships "
                "WHERE hall=? AND status='faol' ORDER BY id DESC LIMIT 30", (hname,)).fetchall()]
            schedule = [dict(r) for r in db.execute(
                "SELECT id,coach,title,kind,cdate,ctime,seats,booked,price FROM coach_schedule WHERE hall=? "
                "AND cdate>=? ORDER BY cdate,ctime LIMIT 40", (hname, time.strftime("%Y-%m-%d"))).fetchall()]
            try:
                anns = [dict(r) for r in db.execute(
                    "SELECT id,title,body,created FROM announcements WHERE hall=? ORDER BY id DESC LIMIT 5", (hname,)).fetchall()]
            except Exception:
                anns = []
            db.close()
            return self.json(200, {"hall": hall, "packages": packages,
                                   "memberships": memberships, "schedule": schedule, "announcements": anns})

        # --- APK integratsiya: abonementni tekshirish (kirish uskunasi / yuzni tanish) ---
        if path.startswith("/api/public/hall/") and not path.endswith("/abonements") and ("/abonement-check" in path or path.endswith("/abonement")) and self.command in ("GET", "POST"):
            try:
                hid = int(path.split("/")[4])
            except (ValueError, IndexError):
                return self.json(400, {"error": "id noto'g'ri"})
            phone = ""
            passport = ""
            if self.command == "GET":
                q = urlparse(self.path)
                prm = dict(urllib.parse.parse_qsl(q.query))
                phone = (prm.get("phone") or "").strip()
                passport = (prm.get("passport") or "").strip()
            else:
                try:
                    raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                    d = json.loads(raw.decode("utf-8"))
                except Exception:
                    return self.json(400, {"error": "JSON noto'g'ri"})
                phone = (d.get("phone") or "").strip()
                passport = (d.get("passport") or "").strip()
            db = get_db()
            h = db.execute("SELECT * FROM halls WHERE id=? AND status='active'", (hid,)).fetchone()
            if not h:
                db.close()
                return self.json(404, {"error": "zal topilmadi"})
            hname = h["name"] or ""
            cond = "hall=? AND status='faol'"
            args = [hname]
            if phone and passport:
                cond += " AND (phone=? OR passport=?)"
                args += [phone, passport]
            elif phone:
                cond += " AND phone=?"
                args.append(phone)
            elif passport:
                cond += " AND passport=?"
                args.append(passport)
            else:
                db.close()
                return self.json(400, {"error": "telefon yoki passport kerak"})
            rows = db.execute("SELECT * FROM memberships WHERE " + cond + " ORDER BY end DESC", args).fetchall()
            today = datetime.date.today().isoformat()
            out = []
            for m in rows:
                st = "faol"
                if m["end"] and m["end"] < today:
                    st = "tugagan"
                if st == "faol" and m["type"] == "sessiyali" and (m["sessions_total"] or 0) > 0 and (m["sessions_used"] or 0) >= m["sessions_total"]:
                    st = "tugagan"
                out.append({
                    "client": m["client"], "phone": m["phone"], "type": m["type"],
                    "package": m["package"], "end": m["end"], "status": st,
                    "sessions_total": m["sessions_total"], "sessions_used": m["sessions_used"],
                    "days_left": (datetime.date.fromisoformat(m["end"]) - datetime.date.today()).days if (st == "faol" and m["end"]) else None,
                })
            db.close()
            return self.json(200, {"ok": True, "hall": hname, "found": len(out) > 0, "abonements": out})

        # --- APK integratsiya: abonementlar ro'yxati (sinxronlash; shaxsiy foto/passport yuborilmaydi) ---
        if path.startswith("/api/public/hall/") and path.endswith("/abonements") and self.command == "GET":
            try:
                hid = int(path.split("/")[4])
            except (ValueError, IndexError):
                return self.json(400, {"error": "id noto'g'ri"})
            db = get_db()
            h = db.execute("SELECT * FROM halls WHERE id=? AND status='active'", (hid,)).fetchone()
            if not h:
                db.close()
                return self.json(404, {"error": "zal topilmadi"})
            rows = db.execute(
                "SELECT id,client,type,sessions_total,sessions_used,start,end,status,package FROM memberships WHERE hall=?",
                (h["name"] or "",)).fetchall()
            today = datetime.date.today().isoformat()
            out = []
            for m in rows:
                st = m["status"]
                if st == "faol" and m["end"] and m["end"] < today:
                    st = "tugagan"
                out.append({"id": m["id"], "client": m["client"], "type": m["type"],
                            "package": m["package"], "end": m["end"], "status": st,
                            "sessions_total": m["sessions_total"], "sessions_used": m["sessions_used"]})
            db.close()
            return self.json(200, {"ok": True, "hall": h["name"], "count": len(out), "abonements": out})

        if path == "/api/halls" and self.command == "POST":
            u = self.current_user()
            if not (u and (u.get("super") or u.get("role") in ("CEO", "Operator"))):
                return self.json(403, {"error": "Kirish taqiqlangan"})
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                data = json.loads(raw.decode("utf-8"))
            except Exception:
                return self.json(400, {"error": "JSON noto'g'ri"})
            name = (data.get("name") or "").strip()
            if not name:
                return self.json(400, {"error": "name bo'sh bo'lishi mumkin emas"})
            db = get_db()
            details_raw = json.dumps(data.get("details") or {}, ensure_ascii=False)
            cur = db.execute(
                "INSERT INTO halls(name, owner, status, phone, branch, commission, login, created, type, details, pass) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    name,
                    (data.get("owner") or "").strip() or "—",
                    (data.get("status") or "active").strip() or "active",
                    (data.get("phone") or "").strip() or "—",
                    int(data.get("branch") or 1),
                    (data.get("commission") or "—").strip() or "—",
                    (data.get("login") or "").strip(),
                    time.strftime("%Y-%m-%d %H:%M"),
                    (data.get("type") or "boshqa").strip() or "boshqa",
                    details_raw,
                    str(data.get("pass") or "").strip(),
                ),
            )
            db.commit()
            row = db.execute("SELECT * FROM halls WHERE id=?", (cur.lastrowid,)).fetchone()
            db.close()
            return self.json(201, row_to_hall(row))

        if path.startswith("/api/halls/") and self.command == "PUT":
            u = self.current_user()
            if not (u and (u.get("super") or u.get("role") in ("CEO", "Operator"))):
                return self.json(403, {"error": "Kirish taqiqlangan"})
            try:
                hid = int(path.split("/")[-1])
            except ValueError:
                return self.json(400, {"error": "id noto'g'ri"})
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                data = json.loads(raw.decode("utf-8"))
            except Exception:
                return self.json(400, {"error": "JSON noto'g'ri"})
            db = get_db()
            details_raw = json.dumps(data.get("details") or {}, ensure_ascii=False)
            cur = db.execute(
                "UPDATE halls SET name=?, owner=?, status=?, phone=?, branch=?, commission=?, login=?, type=?, details=? WHERE id=?",
                (
                    (data.get("name") or "").strip(),
                    (data.get("owner") or "").strip() or "—",
                    (data.get("status") or "active").strip(),
                    (data.get("phone") or "").strip() or "—",
                    int(data.get("branch") or 1),
                    (data.get("commission") or "—").strip() or "—",
                    (data.get("login") or "").strip(),
                    (data.get("type") or "boshqa").strip() or "boshqa",
                    details_raw,
                    hid,
                ),
            )
            # Parol faqat kiritilgan bo'lsa yangilanadi (bo'sh qolsa eskisi saqlanadi)
            if str(data.get("pass") or "").strip():
                db.execute("UPDATE halls SET pass=? WHERE id=?", (str(data["pass"]).strip(), hid))
            db.commit()
            row = db.execute("SELECT * FROM halls WHERE id=?", (hid,)).fetchone()
            db.close()
            if row is None:
                return self.json(404, {"error": "topilmadi"})
            return self.json(200, row_to_hall(row))

        if path.startswith("/api/halls/") and self.command == "DELETE":
            u = self.current_user()
            if not (u and (u.get("super") or u.get("role") in ("CEO", "Operator"))):
                return self.json(403, {"error": "Kirish taqiqlangan"})
            try:
                hid = int(path.split("/")[-1])
            except ValueError:
                return self.json(400, {"error": "id noto'g'ri"})
            db = get_db()
            cur = db.execute("DELETE FROM halls WHERE id=?", (hid,))
            db.commit()
            db.close()
            if cur.rowcount == 0:
                return self.json(404, {"error": "topilmadi"})
            return self.json(200, {"ok": True})

        # ---------- Korporativ paketlar ----------
        if path == "/api/corp-packages" and self.command == "GET":
            db = get_db()
            rows = db.execute("SELECT * FROM corp_packages ORDER BY sort, id").fetchall()
            db.close()
            return self.json(200, [row_to_pkg(r) for r in rows])

        if path == "/api/corp-packages" and self.command == "POST":
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                data = json.loads(raw.decode("utf-8"))
            except Exception:
                return self.json(400, {"error": "JSON noto'g'ri"})
            name = (data.get("name") or "").strip()
            if not name:
                return self.json(400, {"error": "name bo'sh bo'lishi mumkin emas"})
            db = get_db()
            cur = db.execute(
                "INSERT INTO corp_packages(name, seats, price, sort, commission) VALUES(?,?,?,?,?)",
                (
                    name,
                    int(data.get("seats") or 0),
                    int(data.get("price") or 0),
                    int(data.get("sort") or 0),
                    int(data.get("commission") or 0),
                ),
            )
            db.commit()
            row = db.execute("SELECT * FROM corp_packages WHERE id=?", (cur.lastrowid,)).fetchone()
            db.close()
            return self.json(201, row_to_pkg(row))

        if path.startswith("/api/corp-packages/") and self.command == "PUT":
            try:
                pid_ = int(path.split("/")[-1])
            except ValueError:
                return self.json(400, {"error": "id noto'g'ri"})
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                data = json.loads(raw.decode("utf-8"))
            except Exception:
                return self.json(400, {"error": "JSON noto'g'ri"})
            db = get_db()
            cur = db.execute(
                "UPDATE corp_packages SET name=?, seats=?, price=?, sort=?, commission=? WHERE id=?",
                (
                    (data.get("name") or "").strip(),
                    int(data.get("seats") or 0),
                    int(data.get("price") or 0),
                    int(data.get("sort") or 0),
                    int(data.get("commission") or 0),
                    pid_,
                ),
            )
            db.commit()
            row = db.execute("SELECT * FROM corp_packages WHERE id=?", (pid_,)).fetchone()
            db.close()
            if row is None:
                return self.json(404, {"error": "topilmadi"})
            return self.json(200, row_to_pkg(row))

        if path.startswith("/api/corp-packages/") and self.command == "DELETE":
            try:
                pid_ = int(path.split("/")[-1])
            except ValueError:
                return self.json(400, {"error": "id noto'g'ri"})
            db = get_db()
            cur = db.execute("DELETE FROM corp_packages WHERE id=?", (pid_,))
            db.commit()
            db.close()
            if cur.rowcount == 0:
                return self.json(404, {"error": "topilmadi"})
            return self.json(200, {"ok": True})

        # ---------- To'lovlar va checklar ----------
        if path == "/api/payments" and self.command == "GET":
            db = get_db()
            rows = db.execute(
                "SELECT p.*, c.name AS corp_name FROM corp_payments p LEFT JOIN corporate c ON c.id = p.corp_id ORDER BY p.id DESC"
            ).fetchall()
            db.close()
            return self.json(200, [row_to_pay(r) for r in rows])

        if path == "/api/payments" and self.command == "POST":
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                data = json.loads(raw.decode("utf-8"))
            except Exception:
                return self.json(400, {"error": "JSON noto'g'ri"})
            try:
                corp_id = int(data.get("corp_id") or 0)
            except Exception:
                corp_id = 0
            amount = (data.get("amount") or "").strip() or "—"
            commission = (data.get("commission") or "").strip() or "0"
            method = (data.get("method") or "bank").strip() or "bank"
            pdate = (data.get("pdate") or "").strip()
            operator = (data.get("operator") or "Operator").strip()
            details_raw = json.dumps(data.get("details") or {}, ensure_ascii=False)
            db = get_db()
            cur = db.execute(
                "INSERT INTO corp_payments(corp_id, receipt_no, amount, commission, method, pdate, status, operator, created, details) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (corp_id, "", amount, commission, method, pdate, "paid", operator, time.strftime("%Y-%m-%d %H:%M"), details_raw),
            )
            pid_ = cur.lastrowid
            receipt_no = "ELG-%04d-%06d" % (time.localtime().tm_year, pid_)
            db.execute("UPDATE corp_payments SET receipt_no=? WHERE id=?", (receipt_no, pid_))
            db.commit()
            row = db.execute(
                "SELECT p.*, c.name AS corp_name FROM corp_payments p LEFT JOIN corporate c ON c.id = p.corp_id WHERE p.id=?",
                (pid_,),
            ).fetchone()
            db.close()
            return self.json(201, row_to_pay(row))

        if path.startswith("/api/payments/verify/") and self.command == "GET":
            rno = path.split("/")[-1]
            db = get_db()
            row = db.execute(
                "SELECT p.*, c.name AS corp_name FROM corp_payments p LEFT JOIN corporate c ON c.id = p.corp_id WHERE p.receipt_no=?",
                (rno,),
            ).fetchone()
            db.close()
            if row is None:
                return self.json(404, {"ok": False, "error": "check topilmadi"})
            p = row_to_pay(row)
            return self.json(200, {"ok": True, "receipt_no": p["receipt_no"], "corp": p["corp_name"], "amount": p["amount"], "pdate": p["pdate"], "status": p["status"]})

        if path.startswith("/api/payments/") and self.command == "DELETE":
            try:
                pid_ = int(path.split("/")[-1])
            except ValueError:
                return self.json(400, {"error": "id noto'g'ri"})
            db = get_db()
            cur = db.execute("DELETE FROM corp_payments WHERE id=?", (pid_,))
            db.commit()
            db.close()
            if cur.rowcount == 0:
                return self.json(404, {"error": "topilmadi"})
            return self.json(200, {"ok": True})

        # ---------- Korporativ mijozlar (B2B) ----------
        if path == "/api/corporate" and self.command == "GET":
            db = get_db()
            rows = db.execute("SELECT * FROM corporate ORDER BY id DESC").fetchall()
            db.close()
            return self.json(200, [row_to_corp(r) for r in rows])

        if path == "/api/corporate" and self.command == "POST":
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                data = json.loads(raw.decode("utf-8"))
            except Exception:
                return self.json(400, {"error": "JSON noto'g'ri"})
            name = (data.get("name") or "").strip()
            if not name:
                return self.json(400, {"error": "name bo'sh bo'lishi mumkin emas"})
            db = get_db()
            details_raw = json.dumps(data.get("details") or {}, ensure_ascii=False)
            cur = db.execute(
                "INSERT INTO corporate(name, contact, phone, email, inn, status, plan, employees, amount, start, end, created, details) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    name,
                    (data.get("contact") or "").strip() or "—",
                    (data.get("phone") or "").strip() or "—",
                    (data.get("email") or "").strip() or "—",
                    (data.get("inn") or "").strip() or "—",
                    (data.get("status") or "yangi").strip() or "yangi",
                    (data.get("plan") or "oylik").strip() or "oylik",
                    int(data.get("employees") or 0),
                    (data.get("amount") or "—").strip() or "—",
                    (data.get("start") or "").strip(),
                    (data.get("end") or "").strip(),
                    time.strftime("%Y-%m-%d %H:%M"),
                    details_raw,
                ),
            )
            db.commit()
            row = db.execute("SELECT * FROM corporate WHERE id=?", (cur.lastrowid,)).fetchone()
            db.close()
            return self.json(201, row_to_corp(row))

        if path.startswith("/api/corporate/") and self.command == "PUT":
            try:
                cid = int(path.split("/")[-1])
            except ValueError:
                return self.json(400, {"error": "id noto'g'ri"})
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                data = json.loads(raw.decode("utf-8"))
            except Exception:
                return self.json(400, {"error": "JSON noto'g'ri"})
            db = get_db()
            details_raw = json.dumps(data.get("details") or {}, ensure_ascii=False)
            cur = db.execute(
                "UPDATE corporate SET name=?, contact=?, phone=?, email=?, inn=?, status=?, plan=?, employees=?, amount=?, start=?, end=?, details=? WHERE id=?",
                (
                    (data.get("name") or "").strip(),
                    (data.get("contact") or "").strip() or "—",
                    (data.get("phone") or "").strip() or "—",
                    (data.get("email") or "").strip() or "—",
                    (data.get("inn") or "").strip() or "—",
                    (data.get("status") or "yangi").strip() or "yangi",
                    (data.get("plan") or "oylik").strip() or "oylik",
                    int(data.get("employees") or 0),
                    (data.get("amount") or "—").strip() or "—",
                    (data.get("start") or "").strip(),
                    (data.get("end") or "").strip(),
                    details_raw,
                    cid,
                ),
            )
            db.commit()
            row = db.execute("SELECT * FROM corporate WHERE id=?", (cid,)).fetchone()
            db.close()
            if row is None:
                return self.json(404, {"error": "topilmadi"})
            return self.json(200, row_to_corp(row))

        if path.startswith("/api/corporate/") and self.command == "DELETE":
            try:
                cid = int(path.split("/")[-1])
            except ValueError:
                return self.json(400, {"error": "id noto'g'ri"})
            db = get_db()
            cur = db.execute("DELETE FROM corporate WHERE id=?", (cid,))
            db.commit()
            db.close()
            if cur.rowcount == 0:
                return self.json(404, {"error": "topilmadi"})
            return self.json(200, {"ok": True})

        if path == "/api/employees" and self.command == "GET":
            db = get_db()
            rows = db.execute("SELECT * FROM employees ORDER BY id").fetchall()
            db.close()
            u = self.current_user()
            is_op = bool(u and (u.get("super") or u.get("role") in ("CEO", "Operator")))
            out = [row_to_emp(r) for r in rows]
            if not is_op:  # xavfsizlik: parol faqat operatorga ko'rinadi
                for e in out:
                    e.pop("pass", None)
            return self.json(200, out)

        if path == "/api/employees/sync" and self.command in ("PUT", "POST"):
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                data = json.loads(raw.decode("utf-8"))
            except Exception:
                return self.json(400, {"error": "JSON noto'g'ri"})
            if not isinstance(data, list):
                return self.json(400, {"error": "ro'yxat kerak"})
            db = get_db()
            for e in data:
                lg = (e.get("login") or "").strip()
                if not lg:
                    continue
                vals = (
                    (e.get("name") or ""),
                    (e.get("role") or "Boshqa"),
                    (e.get("pass") or ""),
                    (e.get("status") or "faol"),
                    json.dumps(e.get("perms") or [], ensure_ascii=False),
                    int(e.get("brought") or 0),
                    int(e.get("deals") or 0),
                    (e.get("conv") or ""),
                    (e.get("photo") or ""),
                    (e.get("note") or ""),
                    (e.get("last_active") or ""),
                )
                row = db.execute("SELECT id, pass AS oldpass FROM employees WHERE lower(login)=lower(?)", (lg,)).fetchone()
                if row:
                    # Bo'sh parol yuborilsa eski parol saqlanadi (tasodifan o'chirilmasin)
                    pvals = list(vals)
                    if not (e.get("pass") or ""):
                        pvals[2] = row["oldpass"] or ""
                    db.execute(
                        "UPDATE employees SET name=?, role=?, pass=?, status=?, perms=?, brought=?, deals=?, conv=?, photo=?, note=?, last_active=? WHERE id=?",
                        tuple(pvals) + (row["id"],),
                    )
                else:
                    db.execute(
                        "INSERT INTO employees(name, role, login, pass, status, perms, brought, deals, conv, photo, note, created, last_active) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        vals[0:2] + (lg,) + vals[2:10] + ((e.get("created") or ""),) + vals[10:],
                    )
            db.commit()
            db.close()
            return self.json(200, {"ok": True, "count": len(data)})

        if path.startswith("/api/employees/delete/") and self.command == "DELETE":
            lg = path.split("/api/employees/delete/")[1]
            db = get_db()
            cur = db.execute("DELETE FROM employees WHERE lower(login)=lower(?)", (lg,))
            db.commit()
            db.close()
            if cur.rowcount == 0:
                return self.json(404, {"error": "topilmadi"})
            return self.json(200, {"ok": True})

        if path == "/api/auth/captcha" and self.command == "GET":
            token, data_url = _new_captcha()
            return self.json(200, {"token": token, "img": data_url})

        if path == "/api/auth/captcha/check" and self.command == "POST":
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                d = json.loads(raw.decode("utf-8"))
            except Exception:
                return self.json(400, {"error": "JSON noto'g'ri"})
            token = str(d.get("token") or "")
            code = str(d.get("code") or "").strip().lower()
            rec = CAPTCHAS.pop(token, None)
            if not rec:
                return self.json(200, {"ok": False, "reason": "expired"})
            return self.json(200, {"ok": rec["code"] == code})

        if path == "/api/upload" and self.command == "POST":
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                d = json.loads(raw.decode("utf-8"))
            except Exception:
                return self.json(400, {"error": "JSON noto'g'ri"})
            flist = (d.get("files") or [])[:5]
            saved = []
            for f in flist:
                try:
                    name = re.sub(r"[^\w.\-\u0400-\u04FF]", "_", os.path.basename(str(f.get("name") or "fayl")))
                    if not name or len(name) > 80: name = "fayl"
                    data_url = str(f.get("dataUrl") or "")
                    if not data_url.startswith("data:"):
                        continue
                    raw_b64 = data_url.split(",", 1)[1]
                    if len(raw_b64) > 14 * 1024 * 1024:
                        continue
                    import base64 as _b64
                    blob = _b64.b64decode(raw_b64)
                    import uuid as _uuid
                    rel = "uploads/tasks/" + _uuid.uuid4().hex[:8] + "_" + name
                    with open(os.path.join(ROOT, rel), "wb") as fh:
                        fh.write(blob)
                    saved.append({"name": name, "url": "/" + rel})
                except Exception:
                    continue
            return self.json(200, {"files": saved})

        if path == "/api/tasks" and self.command == "GET":
            db = get_db()
            _promote_tasks(db)
            _archive_tasks(db)
            _remind_tasks(db)
            u = self.current_user()
            if self.is_ceo(u):
                _weekly_report(db)
            pr = dict(urllib.parse.parse_qsl(urlparse(self.path).query))
            f_status = (pr.get("status") or "").strip()
            f_pri = (pr.get("priority") or "").strip()
            f_emp = (pr.get("emp") or "").strip().lower()
            f_q = (pr.get("q") or "").strip().lower()
            rows = db.execute("SELECT * FROM tasks ORDER BY id DESC").fetchall()
            names = {}
            for e in db.execute("SELECT login, name FROM employees").fetchall():
                names[str(e["login"] or "").lower()] = e["name"] or e["login"]
            sup = self.super_settings()
            names[str(sup.get("login") or "").lower()] = sup.get("name") or "Super Admin"
            db.close()
            out = []
            for r in rows:
                d = _task_dict(r, names)
                if d["archived"] and not pr.get("all"):
                    continue
                if f_status and d["status"] != f_status:
                    continue
                if f_pri and d["priority"] != f_pri:
                    continue
                if f_emp and f_emp not in [str(x).lower() for x in d["assigned"]]:
                    continue
                if f_q and f_q not in ((d["title"] or "") + " " + (d["text"] or "")).lower():
                    continue
                out.append(d)
            return self.json(200, out)

        if path == "/api/tasks" and self.command == "POST":
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                d = json.loads(raw.decode("utf-8"))
            except Exception:
                return self.json(400, {"error": "JSON noto'g'ri"})
            title = str(d.get("title") or "").strip()[:200]
            if not title:
                return self.json(400, {"error": "Topshiriq nomi kerak"})
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            plan_date = str(d.get("plan_date") or "").strip()[:20]
            photo_req = 1 if d.get("photo_required") else 0
            status = "reja" if (plan_date and plan_date > datetime.date.today().isoformat()) else "yangi"
            db = get_db()
            cur = db.execute(
                "INSERT INTO tasks(title,text,deadline,priority,files,status,assigned,created_by,created,photo_required,plan_date,category) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (title, str(d.get("text") or "")[:2000], str(d.get("deadline") or "")[:20],
                 str(d.get("priority") or "orta")[:20],
                 json.dumps((d.get("files") or [])[:5], ensure_ascii=False),
                 status,
                 json.dumps((d.get("assigned") or [])[:50], ensure_ascii=False),
                 str(d.get("created_by") or "")[:100], now, photo_req, plan_date,
                 str(d.get("category") or "")[:50]))
            tid = cur.lastrowid
            if status == "yangi":
                t = _task_dict(db.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone())
                for lg in t["assigned"]:
                    _chat_card_task(db, t, lg)
            db.commit()
            db.close()
            return self.json(200, {"id": tid, "status": status})

        if path.startswith("/api/tasks/") and self.command == "PUT":
            tid_s = path[len("/api/tasks/"):].strip("/")
            try:
                tid = int(tid_s)
            except Exception:
                return self.json(400, {"error": "ID noto'g'ri"})
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                d = json.loads(raw.decode("utf-8"))
            except Exception:
                return self.json(400, {"error": "JSON noto'g'ri"})
            db = get_db()
            row = db.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
            if not row:
                db.close()
                return self.json(404, {"error": "Topshiriq topilmadi"})
            t = _task_dict(row)
            # Tahrirlash (CEO): maydonlar berilgan bo'lsa yangilanadi
            upd = {}
            for k in ("title", "text", "deadline", "priority", "created_by", "category"):
                if k in d:
                    upd[k] = str(d.get(k) or "")[:2000] if k == "text" else str(d.get(k) or "")[:200]
            if "files" in d:
                upd["files"] = json.dumps((d.get("files") or [])[:5], ensure_ascii=False)
            if "assigned" in d:
                upd["assigned"] = json.dumps((d.get("assigned") or [])[:50], ensure_ascii=False)
            if "photo_required" in d:
                upd["photo_required"] = 1 if d.get("photo_required") else 0
            if "plan_date" in d:
                upd["plan_date"] = str(d.get("plan_date") or "")[:20]
            if "deadline" in d or "status" in d or "category" in d:
                upd["reminded"] = 0
            status = str(d.get("status") or "")
            if status:
                allowed = {"yangi", "qabul", "bajarildi", "rad", "reja"}
                if status not in allowed:
                    status = ""
            done_note = d.get("done_note")
            if done_note is None: done_note = t["done_note"]
            else: upd["done_note"] = str(done_note)[:3000]
            done_files = d.get("done_files")
            if done_files is None: done_files = t["done_files"]
            else: upd["done_files"] = json.dumps((done_files or [])[:5], ensure_ascii=False)
            done_at = t["done_at"]
            if status in ("bajarildi", "rad") and not done_at:
                done_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            if status:
                if status == "bajarildi" and (t["photo_required"] or upd.get("photo_required")) and not done_files:
                    db.close()
                    return self.json(400, {"error": "Bu topshiriqda foto hisobot shart — kamida bitta rasm ilova qiling"})
                upd["status"] = status
                upd["done_at"] = done_at
            if upd:
                sets = ", ".join("%s=?" % k for k in upd)
                vals = list(upd.values()) + [tid]
                db.execute("UPDATE tasks SET %s WHERE id=?" % sets, vals)
                # reja vaqti keldi yoki tahrirlab reja->yangi
                nt = _task_dict(db.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone())
                if nt["status"] == "reja" and nt["plan_date"] and nt["plan_date"] <= datetime.date.today().isoformat():
                    db.execute("UPDATE tasks SET status='yangi' WHERE id=?", (tid,))
                    nt["status"] = "yangi"
                    for lg in nt["assigned"]:
                        _chat_card_task(db, nt, lg)
            db.commit()
            db.close()
            return self.json(200, {"ok": True, "status": (upd.get("status") or t["status"])})

        if path.startswith("/api/tasks/") and self.command == "DELETE":
            tid_s = path[len("/api/tasks/"):].strip("/")
            try:
                tid = int(tid_s)
            except Exception:
                return self.json(400, {"error": "ID noto'g'ri"})
            db = get_db()
            db.execute("DELETE FROM tasks WHERE id=?", (tid,))
            db.commit()
            db.close()
            return self.json(200, {"ok": True})

        # ---------- Topshiriq shablonlari (CEO) ----------
        if path == "/api/templates" and self.command == "GET":
            u = self.current_user()
            if not self.is_ceo(u):
                return self.json(403, {"error": "Faqat CEO"})
            try:
                tpl = json.loads(get_setting("tk_templates", "[]"))
            except Exception:
                tpl = []
            return self.json(200, {"templates": tpl})

        if path == "/api/templates" and self.command == "POST":
            u = self.current_user()
            if not self.is_ceo(u):
                return self.json(403, {"error": "Faqat CEO"})
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                d = json.loads(raw.decode("utf-8"))
            except Exception:
                return self.json(400, {"error": "JSON noto'g'ri"})
            title = str(d.get("title") or "").strip()[:200]
            if not title:
                return self.json(400, {"error": "Shablon nomi kerak"})
            try:
                tpl = json.loads(get_setting("tk_templates", "[]"))
            except Exception:
                tpl = []
            item = {"title": title, "text": str(d.get("text") or "")[:2000],
                    "category": str(d.get("category") or "")[:50],
                    "priority": str(d.get("priority") or "orta")[:20],
                    "deadline_days": int(d.get("deadline_days") or 0),
                    "photo_required": 1 if d.get("photo_required") else 0}
            tpl = [t for t in tpl if (t.get("title") or "") != title]
            tpl.append(item)
            set_setting("tk_templates", json.dumps(tpl[-50:], ensure_ascii=False))
            return self.json(200, {"ok": True})

        if path.startswith("/api/templates/") and self.command == "DELETE":
            u = self.current_user()
            if not self.is_ceo(u):
                return self.json(403, {"error": "Faqat CEO"})
            try:
                idx = int(path[len("/api/templates/"):].strip("/"))
            except Exception:
                return self.json(400, {"error": "Indeks noto'g'ri"})
            try:
                tpl = json.loads(get_setting("tk_templates", "[]"))
            except Exception:
                tpl = []
            if 0 <= idx < len(tpl):
                tpl.pop(idx)
                set_setting("tk_templates", json.dumps(tpl, ensure_ascii=False))
            return self.json(200, {"ok": True})

        # ---------- Boshqaruv paneli KPI ----------
        if path == "/api/kpis" and self.command == "GET":
            u = self.current_user()
            if not self.is_ceo(u):
                return self.json(403, {"error": "Faqat CEO"})
            db = get_db()
            _promote_tasks(db)
            _archive_tasks(db)
            _remind_tasks(db)
            _weekly_report(db)
            today = datetime.date.today().isoformat()
            active = db.execute("SELECT COUNT(*) c FROM tasks WHERE archived=0 AND status IN ('yangi','qabul')").fetchone()["c"]
            overdue = db.execute("SELECT COUNT(*) c FROM tasks WHERE archived=0 AND status IN ('yangi','qabul') AND deadline!='' AND deadline<?", (today,)).fetchone()["c"]
            reja = db.execute("SELECT COUNT(*) c FROM tasks WHERE archived=0 AND status='reja'").fetchone()["c"]
            month = today[:7]
            done_month = db.execute("SELECT COUNT(*) c FROM tasks WHERE status='bajarildi' AND done_at LIKE ?", (month + "%",)).fetchone()["c"]
            rep_month = db.execute("SELECT COUNT(*) c FROM daily_reports WHERE created LIKE ?", (month + "%",)).fetchone()["c"]
            att_today = db.execute("SELECT * FROM attendance WHERE date=?", (today,)).fetchall()
            emps = db.execute("SELECT COUNT(*) c FROM employees WHERE status='faol'").fetchone()["c"]
            db.close()
            return self.json(200, {
                "tasks_active": active, "tasks_overdue": overdue, "tasks_reja": reja,
                "tasks_done_month": done_month, "reports_month": rep_month,
                "att": {"keldi": len(att_today), "ketdi": sum(1 for r in att_today if r["checkout"]),
                        "suspicious": sum(1 for r in att_today if r["suspicious"]), "jami": emps}
            })

        if path == "/api/daily" and self.command == "GET":
            db = get_db()
            rows = db.execute("SELECT * FROM daily_reports ORDER BY id DESC").fetchall()
            db.close()
            out = []
            for r in rows:
                out.append({
                    "id": r["id"], "emp": r["emp"], "emp_name": r["emp_name"] or "",
                    "work": r["work"], "period": r["period"] or "",
                    "note": r["note"] or "", "files": json.loads(r["files"] or "[]"),
                    "created": r["created"]
                })
            return self.json(200, out)

        if path == "/api/daily" and self.command == "POST":
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                d = json.loads(raw.decode("utf-8"))
            except Exception:
                return self.json(400, {"error": "JSON noto'g'ri"})
            work = str(d.get("work") or "").strip()[:2000]
            if not work:
                return self.json(400, {"error": "Bajarilgan ish yozilishi kerak"})
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            db = get_db()
            cur = db.execute(
                "INSERT INTO daily_reports(emp,emp_name,work,period,note,files,created) VALUES(?,?,?,?,?,?,?)",
                (str(d.get("emp") or "")[:100], str(d.get("emp_name") or "")[:200],
                 work, str(d.get("period") or "")[:50], str(d.get("note") or "")[:1000],
                 json.dumps((d.get("files") or [])[:5], ensure_ascii=False), now))
            db.commit()
            rid = cur.lastrowid
            db.close()
            return self.json(200, {"id": rid})

        # ---------- Hisobotlar (oylik / yillik) ----------
        if path == "/api/reports" and self.command == "GET":
            q = dict(urllib.parse.parse_qsl(urlparse(self.path).query))
            emp = (q.get("emp") or "").lower()
            frm = (q.get("from") or "").strip()
            to = (q.get("to") or "").strip()
            db = get_db()
            if frm and to:
                trows = db.execute("SELECT * FROM tasks WHERE status='bajarildi' AND done_at>=? AND done_at<=? ORDER BY done_at DESC", (frm + " 00:00", to + " 23:59")).fetchall()
                drows = db.execute("SELECT * FROM daily_reports WHERE created>=? AND created<=? ORDER BY created DESC", (frm + " 00:00", to + " 23:59")).fetchall()
            else:
                trows = db.execute("SELECT * FROM tasks WHERE status='bajarildi' ORDER BY done_at DESC").fetchall()
                drows = db.execute("SELECT * FROM daily_reports ORDER BY created DESC").fetchall()
            db.close()
            tasks = []
            for r in trows:
                d = _task_dict(r)
                if emp and emp not in [str(x).lower() for x in d["assigned"]]:
                    continue
                tasks.append(d)
            dails = []
            for r in drows:
                x = {"id": r["id"], "emp": r["emp"], "emp_name": r["emp_name"] or "", "work": r["work"],
                     "period": r["period"] or "", "note": r["note"] or "", "files": json.loads(r["files"] or "[]"),
                     "created": r["created"]}
                if emp and str(x["emp"]).lower() != emp:
                    continue
                dails.append(x)
            return self.json(200, {"tasks": tasks, "dailies": dails})

        # ---------- Xodimlar hisobotlari ZIP (CEO) ----------
        if path == "/api/employees/reports-zip" and self.command == "GET":
            u = self.current_user()
            if not self.is_ceo(u):
                return self.json(403, {"error": "Faqat CEO"})
            q = dict(urllib.parse.parse_qsl(urlparse(self.path).query))
            frm = (q.get("from") or "").strip()
            to_ = (q.get("to") or "").strip()
            if not frm or not to_:
                return self.json(400, {"error": "from va to kerak"})
            import zipfile as _zf, io as _io2
            db = get_db()
            drows = db.execute(
                "SELECT * FROM daily_reports WHERE created>=? AND created<=? ORDER BY emp_name, created",
                (frm + " 00:00", to_ + " 23:59")).fetchall()
            trows = db.execute(
                "SELECT * FROM tasks WHERE status='bajarildi' AND done_at>=? AND done_at<=? ORDER BY done_at",
                (frm + " 00:00", to_ + " 23:59")).fetchall()
            db.close()

            def _zs(s, maxlen=60):
                s = re.sub(r"[^\w.\-\u0400-\u04FF ]", "_", str(s or "")).strip()
                return (s[:maxlen] or "nomalum")

            buf = _io2.BytesIO()
            index_lines = ["Sana\tTuri\tXodim\tMazmun\tFayllar"]
            with _zf.ZipFile(buf, "w", _zf.ZIP_DEFLATED) as z:
                for r in drows:
                    emp = _zs(r["emp_name"] or r["emp"] or "xodim", 40)
                    when = _zs((r["created"] or "")[:16].replace(":", ""), 30)
                    folder = "Xodimlar/%s/Kunlik/%s - %s" % (emp, when, _zs(r["work"], 50))
                    z.writestr(folder + "/hisobot.txt",
                               "Xodim: %s\nSana: %s\nDavr: %s\n\nBajargan ish:\n%s\n" % (
                                   r["emp_name"] or r["emp"], r["created"], r["period"], r["work"] or ""))
                    names = []
                    for f in (json.loads(r["files"] or "[]")):
                        url = str(f.get("url") or "")
                        if url.startswith("/uploads/"):
                            p = os.path.join(ROOT, url.lstrip("/").replace("/", os.sep))
                            if os.path.exists(p):
                                z.write(p, folder + "/" + _zs(f.get("name"), 60))
                                names.append(str(f.get("name")))
                    index_lines.append("%s\tKunlik\t%s\t%s\t%s" % (
                        r["created"], r["emp_name"] or r["emp"],
                        str(r["work"] or "").replace("\t", " ")[:200], ", ".join(names)))
                for t in trows:
                    td = _task_dict(t)
                    for lg in (td["assigned"] or []):
                        emp = _zs(lg, 40)
                        when = _zs((td["done_at"] or "")[:16].replace(":", ""), 30)
                        folder = "Xodimlar/%s/Topshiriqlar/%s - %s" % (emp, when, _zs(td["title"], 50))
                        z.writestr(folder + "/topshiriq.txt",
                                   "Topshiriq: %s\nBajarilgan: %s\nIzoh: %s\n" % (
                                       td["title"], td["done_at"], td["done_note"] or ""))
                        names = []
                        for f in (td["done_files"] or []):
                            url = str(f.get("url") or "")
                            if url.startswith("/uploads/"):
                                p = os.path.join(ROOT, url.lstrip("/").replace("/", os.sep))
                                if os.path.exists(p):
                                    z.write(p, folder + "/" + _zs(f.get("name"), 60))
                                    names.append(str(f.get("name")))
                        index_lines.append("%s\tTopshiriq\t%s\t%s\t%s" % (
                            td["done_at"], lg, str(td["title"] or "").replace("\t", " ")[:200], ", ".join(names)))
                z.writestr("INDEX.tsv", "\n".join(index_lines))
            body = buf.getvalue()
            fname = "hisobotlar_%s_%s.zip" % (frm, to_)
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", 'attachment; filename="%s"' % fname)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return None

        # ---------- Davomat settings (CEO) ----------
        if path == "/api/attendance/settings" and self.command == "GET":
            u = self.current_user()
            if not self.is_ceo(u):
                return self.json(403, {"error": "Faqat CEO"})
            return self.json(200, {
                "enabled": get_setting("att_enabled", "1"),
                "lat": get_setting("att_lat", "41.2995"),
                "lon": get_setting("att_lon", "69.2401"),
                "radius": get_setting("att_radius", "100"),
                "tg_token": get_setting("tg_token", ""),
                "tg_chat": get_setting("tg_chat", ""),
                "work_days": get_setting("att_work_days", "1,2,3,4,5"),
                "start_time": get_setting("att_start", "09:00"),
                "end_time": get_setting("att_end", "18:00"),
                "lunch_start": get_setting("att_lunch_start", "13:00"),
                "lunch_end": get_setting("att_lunch_end", "14:00"),
                "grace_min": get_setting("att_grace", "5")
            })

        if path == "/api/attendance/settings" and self.command == "POST":
            u = self.current_user()
            if not self.is_ceo(u):
                return self.json(403, {"error": "Faqat CEO"})
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                d = json.loads(raw.decode("utf-8"))
            except Exception:
                return self.json(400, {"error": "JSON noto'g'ri"})
            if "enabled" in d: set_setting("att_enabled", "1" if d["enabled"] else "0")
            if "lat" in d: set_setting("att_lat", str(d["lat"]).split(",")[0].strip())
            if "lon" in d: set_setting("att_lon", str(d["lon"]).split(",")[0].strip())
            if "radius" in d: set_setting("att_radius", str(max(10, int(float(d["radius"])))))
            if "tg_token" in d: set_setting("tg_token", str(d["tg_token"]).strip())
            if "tg_chat" in d: set_setting("tg_chat", str(d["tg_chat"]).strip())
            if "work_days" in d:
                wd = [x.strip() for x in str(d["work_days"]).split(",") if x.strip() in "1234567"]
                set_setting("att_work_days", ",".join(sorted(wd)) or "1,2,3,4,5")
            if "start_time" in d: set_setting("att_start", str(d["start_time"]).strip()[:5] or "09:00")
            if "end_time" in d: set_setting("att_end", str(d["end_time"]).strip()[:5] or "18:00")
            if "lunch_start" in d: set_setting("att_lunch_start", str(d["lunch_start"]).strip()[:5] or "13:00")
            if "lunch_end" in d: set_setting("att_lunch_end", str(d["lunch_end"]).strip()[:5] or "14:00")
            if "grace_min" in d:
                try:
                    set_setting("att_grace", str(int(float(d["grace_min"]))))
                except Exception:
                    set_setting("att_grace", "5")
            return self.json(200, {"ok": True})

        # ---------- Davomat: keldim / ketdim ----------
        def _att_check(u, action):
            if get_setting("att_enabled", "1") != "1":
                return None, "Davomat hozircha o'chirilgan — CEO sozlamalarda yoqsin"
            def _fnum(v, dflt):
                try:
                    v = str(v).strip().split(",")[0].strip()
                    return float(v)
                except Exception:
                    return dflt
            lat = _fnum(d.get("lat"), 0); lon = _fnum(d.get("lon"), 0)
            olat = _fnum(get_setting("att_lat", "41.2995"), 41.2995)
            olon = _fnum(get_setting("att_lon", "69.2401"), 69.2401)
            radius = int(float(get_setting("att_radius", "100")))
            dist = haversine_m(lat, lon, olat, olon)
            if dist > radius:
                return None, "Siz ofisdan %.0f m uzoqdasiz — «Keldim / Ketdim» faqat ofis hududida ishlaydi (ruxsat: %.0f m)" % (dist, radius)
            photo = (d.get("photo") or "").strip()
            if not photo or (photo and not photo.startswith("data:")):
                return None, "Davomatni tasdiqlash uchun jonli foto (kamera orqali) majburiy"
            return {"dist": dist, "radius": radius}, None

        if path == "/api/attendance/checkin" and self.command == "POST":
            u = self.current_user()
            if u is None:
                return self.json(403, {"error": "Avtorizatsiya talab qilinadi"})
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                d = json.loads(raw.decode("utf-8"))
            except Exception:
                return self.json(400, {"error": "JSON noto'g'ri"})
            chk, err = _att_check(u, "in")
            if err:
                return self.json(400, {"error": err})
            lg = (u.get("login") or "").lower()
            today = datetime.date.today().isoformat()
            hm = time.strftime("%H:%M")
            db = get_db()
            row = db.execute("SELECT * FROM attendance WHERE emp=? AND date=?", (lg, today)).fetchone()
            if row and row["checkin"]:
                db.close()
                return self.json(200, {"ok": True, "record": {"emp": row["emp"], "emp_name": row["emp_name"], "date": row["date"], "checkin": row["checkin"], "checkout": row["checkout"] or "", "dist": row["dist"]}})
            if row:
                db.execute("UPDATE attendance SET checkin=?, lat=?, lon=?, dist=?, suspicious=0, photo=? WHERE id=?", (hm, d.get("lat"), d.get("lon"), chk["dist"], d.get("photo") or "", row["id"]))
                rid = row["id"]
            else:
                cur = db.execute("INSERT INTO attendance(emp,emp_name,date,checkin,lat,lon,dist,suspicious,photo,created) VALUES(?,?,?,?,?,?,?,?,?,?)",
                                 (lg, u.get("name") or lg, today, hm, d.get("lat"), d.get("lon"), chk["dist"], 0, d.get("photo") or "", time.strftime("%Y-%m-%d %H:%M")))
                rid = cur.lastrowid
            db.commit()
            db.close()
            send_telegram("👤 %s soat %s keldi (ofisdan %.0f m)" % (u.get("name") or lg, hm, chk["dist"]))
            return self.json(200, {"ok": True, "record": {"emp": lg, "emp_name": u.get("name") or lg, "date": today, "checkin": hm, "checkout": "", "dist": chk["dist"], "suspicious": 0}})

        if path == "/api/attendance/checkout" and self.command == "POST":
            u = self.current_user()
            if u is None:
                return self.json(403, {"error": "Avtorizatsiya talab qilinadi"})
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                d = json.loads(raw.decode("utf-8"))
            except Exception:
                return self.json(400, {"error": "JSON noto'g'ri"})
            chk, err = _att_check(u, "out")
            if err:
                return self.json(400, {"error": err})
            lg = (u.get("login") or "").lower()
            today = datetime.date.today().isoformat()
            hm = time.strftime("%H:%M")
            db = get_db()
            row = db.execute("SELECT * FROM attendance WHERE emp=? AND date=?", (lg, today)).fetchone()
            if not row or not row["checkin"]:
                db.close()
                return self.json(400, {"error": "Avval «Keldim» tugmasini bosing"})
            if row["checkout"]:
                db.close()
                return self.json(200, {"ok": True, "record": {"emp": row["emp"], "emp_name": row["emp_name"], "date": row["date"], "checkin": row["checkin"], "checkout": row["checkout"], "dist": row["dist"]}})
            db.execute("UPDATE attendance SET checkout=?, lat=?, lon=?, dist=?, suspicious=0, photo=? WHERE id=?", (hm, d.get("lat"), d.get("lon"), chk["dist"], d.get("photo") or "", row["id"]))
            db.commit()
            db.close()
            send_telegram("👤 %s soat %s keldi va %s ketdi" % (u.get("name") or lg, row["checkin"], hm))
            return self.json(200, {"ok": True, "record": {"emp": lg, "emp_name": u.get("name") or lg, "date": today, "checkin": row["checkin"], "checkout": hm, "dist": chk["dist"], "suspicious": 0}})

        # ---------- Davomat ro'yxat (CEO) ----------
        def _att_flags(r, date):
            wd = [x.strip() for x in get_setting("att_work_days", "1,2,3,4,5").split(",") if x.strip()]
            st = get_setting("att_start", "09:00").strip()
            en = get_setting("att_end", "18:00").strip()
            late = early = False
            try:
                dty = datetime.date.fromisoformat(str(date)[:10])
                if str(dty.weekday() + 1) in wd:
                    if r and r["checkin"] and st and r["checkin"] > st:
                        late = True
                    if r and r["checkout"] and en and r["checkout"] < en:
                        early = True
            except Exception:
                pass
            susp = bool(r and r["suspicious"])
            if not r:
                base = "yo'q"
            elif susp:
                base = "shubhali"
            elif r["checkout"]:
                base = "ketdi"
            elif r["checkin"]:
                base = "keldi"
            else:
                base = "yo'q"
            return {"suspicious": 1 if susp else 0, "late": 1 if late else 0, "early": 1 if early else 0, "status": base}

        if path == "/api/attendance" and self.command == "GET":
            q = dict(urllib.parse.parse_qsl(urlparse(self.path).query))
            date = (q.get("date") or datetime.date.today().isoformat()).strip()
            month = (q.get("month") or "").strip()
            frm = (q.get("from") or "").strip()
            to_ = (q.get("to") or "").strip()
            emp = (q.get("emp") or "").strip().lower()
            db = get_db()
            if frm and to_:
                sql = "SELECT * FROM attendance WHERE date>=? AND date<=?"
                args = [frm, to_]
                if emp:
                    sql += " AND lower(emp)=?"
                    args.append(emp)
                sql += " ORDER BY date DESC, id DESC"
                rows = db.execute(sql, args).fetchall()
                db.close()
                out = []
                for r in rows:
                    fl = _att_flags(r, r["date"])
                    out.append({"id": r["id"], "emp": r["emp"], "emp_name": r["emp_name"], "date": r["date"],
                                "checkin": r["checkin"], "checkout": r["checkout"] or "", "dist": r["dist"],
                                "suspicious": fl["suspicious"], "late": fl["late"], "early": fl["early"], "status": fl["status"], "photo": (r["photo"] if r else "")})
                return self.json(200, {"from": frm, "to": to_, "rows": out})
            if month:
                rows = db.execute("SELECT * FROM attendance WHERE date LIKE ? ORDER BY date DESC, id DESC", (month + "%",)).fetchall()
                db.close()
                out = []
                for r in rows:
                    fl = _att_flags(r, r["date"])
                    out.append({"id": r["id"], "emp": r["emp"], "emp_name": r["emp_name"], "date": r["date"],
                                "checkin": r["checkin"], "checkout": r["checkout"] or "", "dist": r["dist"],
                                "suspicious": fl["suspicious"], "late": fl["late"], "early": fl["early"], "status": fl["status"], "photo": (r["photo"] if r else "")})
                return self.json(200, {"rows": out})
            emps = db.execute("SELECT login,name,photo FROM employees WHERE status='faol' ORDER BY name").fetchall()
            rows = {r["emp"]: r for r in db.execute("SELECT * FROM attendance WHERE date=?", (date,)).fetchall()}
            db.close()
            out = []
            for e in emps:
                lg = (e["login"] or "").lower()
                r = rows.get(lg)
                fl = _att_flags(r, date)
                out.append({
                    "emp": lg, "emp_name": e["name"] or lg,
                    "checkin": r["checkin"] if r else "", "checkout": r["checkout"] if r else "",
                    "dist": r["dist"] if r else 0,
                    "suspicious": fl["suspicious"], "late": fl["late"], "early": fl["early"], "status": fl["status"], "photo": (r["photo"] if r else "")
                })
            return self.json(200, {"date": date, "rows": out})

        # ---------- Davomat statistika ----------
        if path == "/api/attendance/stats" and self.command == "GET":
            q = dict(urllib.parse.parse_qsl(urlparse(self.path).query))
            date = (q.get("date") or datetime.date.today().isoformat()).strip()
            month = (q.get("month") or date[:7]).strip()
            db = get_db()
            trows = db.execute("SELECT * FROM attendance WHERE date=?", (date,)).fetchall()
            rows = db.execute("SELECT date, COUNT(*) k, SUM(CASE WHEN checkout!='' THEN 1 ELSE 0 END) kd, SUM(suspicious) sp FROM attendance WHERE date LIKE ? GROUP BY date ORDER BY date", (month + "%",)).fetchall()
            emps = db.execute("SELECT COUNT(*) c FROM employees WHERE status='faol'").fetchone()["c"]
            db.close()
            return self.json(200, {
                "date": date,
                "today": {"keldi": len(trows), "ketdi": sum(1 for r in trows if r["checkout"]),
                          "suspicious": sum(1 for r in trows if r["suspicious"]), "jami_xodim": emps},
                "month": [{"date": r["date"], "keldi": r["k"], "ketdi": r["kd"], "suspicious": r["sp"] or 0} for r in rows]
            })

        # ---------- Davomat Excel export ----------
        if path == "/api/attendance/export" and self.command == "GET":
            u = self.current_user()
            if not self.is_ceo(u):
                return self.json(403, {"error": "Faqat CEO"})
            q = dict(urllib.parse.parse_qsl(urlparse(self.path).query))
            date = (q.get("date") or "").strip()
            month = (q.get("month") or "").strip()
            frm = (q.get("from") or "").strip()
            to_ = (q.get("to") or "").strip()
            emp = (q.get("emp") or "").strip().lower()
            db = get_db()
            if frm and to_:
                sql = "SELECT * FROM attendance WHERE date>=? AND date<=?"
                args = [frm, to_]
                if emp:
                    sql += " AND lower(emp)=?"
                    args.append(emp)
                sql += " ORDER BY date, id"
                rows = db.execute(sql, args).fetchall()
                db.close()
                headers = ["Sana", "Xodim", "Keldi", "Ketdi", "Masofa (m)", "Holat"]
                data = []
                flags = []
                for r in rows:
                    fl = _att_flags(r, r["date"])
                    lab = {"yo'q": "Yo'q", "keldi": "Keldi", "ketdi": "Ketdi", "shubhali": "Shubhali"}.get(fl["status"], fl["status"])
                    if fl["late"]:
                        lab += " (kech)"
                    if fl["early"]:
                        lab += " (erta)"
                    if fl["suspicious"]:
                        lab = "Shubhali"
                    data.append([r["date"], r["emp_name"], r["checkin"], r["checkout"] or "-", int(r["dist"] or 0), lab])
                    flags.append([0, 0, 0, 0, 0, 1 if fl["suspicious"] else 0])
                fname = "davomat_%s_%s.xlsx" % (frm, to_)
                body = _xlsx(headers, data, flags)
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                self.send_header("Content-Disposition", 'attachment; filename="%s"' % fname)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return None
            flags = []
            if month:
                rows = db.execute("SELECT * FROM attendance WHERE date LIKE ? ORDER BY date DESC, id DESC", (month + "%",)).fetchall()
                db.close()
                headers = ["Sana", "Xodim", "Keldi", "Ketdi", "Masofa (m)", "Holat"]
                data = []
                for r in rows:
                    fl = _att_flags(r, r["date"])
                    lab = {"yo'q": "Yo'q", "keldi": "Keldi", "ketdi": "Ketdi", "shubhali": "Shubhali"}.get(fl["status"], fl["status"])
                    if fl["late"]:
                        lab += " (kech)"
                    if fl["early"]:
                        lab += " (erta)"
                    if fl["suspicious"]:
                        lab = "Shubhali"
                    data.append([r["date"], r["emp_name"], r["checkin"], r["checkout"] or "-", int(r["dist"] or 0), lab])
                    flags.append([0, 0, 0, 0, 0, 1 if fl["suspicious"] else 0])
                fname = "davomat_%s.xlsx" % month
            else:
                emps = db.execute("SELECT login,name FROM employees WHERE status='faol' ORDER BY name").fetchall()
                rows = {r["emp"]: r for r in db.execute("SELECT * FROM attendance WHERE date=?", (date or datetime.date.today().isoformat(),)).fetchall()}
                db.close()
                headers = ["Xodim", "Keldi", "Ketdi", "Masofa (m)", "Holat"]
                data = []
                for e in emps:
                    r = rows.get((e["login"] or "").lower())
                    fl = _att_flags(r, date or datetime.date.today().isoformat())
                    lab = {"yo'q": "Yo'q", "keldi": "Keldi", "ketdi": "Ketdi", "shubhali": "Shubhali"}.get(fl["status"], fl["status"])
                    if fl["late"] and fl["status"] != "shubhali":
                        lab += " (kech)"
                    if fl["early"] and fl["status"] != "shubhali":
                        lab += " (erta)"
                    if fl["suspicious"]:
                        lab = "Shubhali"
                    data.append([e["name"], r["checkin"] if r else "-", r["checkout"] if r else "-",
                                 int(r["dist"] or 0) if r else "-", lab])
                    flags.append([0, 0, 0, 0, 1 if fl["suspicious"] else 0])
                fname = "davomat_%s.xlsx" % (date or datetime.date.today().isoformat())
            body = _xlsx(headers, data, flags)
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.send_header("Content-Disposition", 'attachment; filename="%s"' % fname)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return None

        if path == "/api/auth/blocked" and self.command == "GET":
            try:
                from urllib.parse import urlsplit, parse_qs
                q = parse_qs(urlsplit(self.path).query)
                device = (q.get("device") or [""])[0] or (self.client_address[0] if self.client_address else "")
            except Exception:
                device = ""
            db = get_db()
            row = db.execute("SELECT blocked_until FROM login_attempts WHERE device=?", (device,)).fetchone()
            db.close()
            now = datetime.datetime.now()
            if row and row["blocked_until"]:
                try:
                    until = datetime.datetime.strptime(row["blocked_until"], "%Y-%m-%d %H:%M:%S")
                except Exception:
                    until = now
                if until > now:
                    left = int((until - now).total_seconds())
                    return self.json(200, {"blocked": True, "until": row["blocked_until"], "left": left})
            return self.json(200, {"blocked": False, "left": 0})

        if path == "/api/auth/attempt" and self.command == "POST":
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                d = json.loads(raw.decode("utf-8"))
            except Exception:
                return self.json(400, {"error": "JSON noto'g'ri"})
            device = (d.get("device") or "").strip() or (self.client_address[0] if self.client_address else "")
            ok = bool(d.get("ok"))
            now = datetime.datetime.now()
            db = get_db()
            row = db.execute("SELECT * FROM login_attempts WHERE device=?", (device,)).fetchone()
            if ok:
                if row:
                    db.execute("DELETE FROM login_attempts WHERE device=?", (device,))
                db.commit()
                db.close()
                return self.json(200, {"blocked": False, "count": 0})
            cnt = (row["count"] if row else 0) + 1
            blocked_until = ""
            if cnt >= 5:
                blocked_until = (now + datetime.timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
            if row:
                db.execute("UPDATE login_attempts SET count=?, blocked_until=?, updated=? WHERE device=?",
                           (cnt, blocked_until, now.strftime("%Y-%m-%d %H:%M:%S"), device))
            else:
                db.execute("INSERT INTO login_attempts(device,count,blocked_until,updated) VALUES(?,?,?,?)",
                           (device, cnt, blocked_until, now.strftime("%Y-%m-%d %H:%M:%S")))
            db.commit()
            db.close()
            return self.json(200, {"blocked": cnt >= 5, "count": cnt, "until": blocked_until, "left": 7200 if cnt >= 5 else 0})

        if path == "/api/auth/super" and self.command == "GET":
            s = self.super_settings()
            # Xavfsizlik: parol hech qachon ochiq qaytmaydi — tekshirish server tomonda
            return self.json(200, {"login": s["login"], "name": s["name"], "photo": s["photo"]})

        if path == "/api/auth/super/check" and self.command == "POST":
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                d = json.loads(raw.decode("utf-8"))
            except Exception:
                return self.json(400, {"error": "JSON noto'g'ri"})
            lg = str(d.get("login") or "").strip()
            pw = str(d.get("password") or "")
            s = self.super_settings()
            if lg.lower() != (s["login"] or "").lower() or pw != (s["pass"] or ""):
                audit(lg or "?", "anonim", "super_login_xato", "operator", "noto'g'ri parol")
                return self.json(200, {"ok": False})
            audit(lg, "CEO", "super_login", "operator", "Operator paneliga kirdi")
            return self.json(200, {"ok": True, "login": s["login"], "name": s["name"] or "Super Admin", "photo": s["photo"] or ""})

        if path == "/api/auth/employee/check" and self.command == "POST":
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                d = json.loads(raw.decode("utf-8"))
            except Exception:
                return self.json(400, {"error": "JSON noto'g'ri"})
            lg = str(d.get("login") or "").strip()
            pw = str(d.get("password") or "")
            db = get_db()
            row = db.execute("SELECT * FROM employees WHERE lower(login)=lower(?)", (lg,)).fetchone()
            db.close()
            if row is None or (row["pass"] or "") != pw:
                audit(lg or "?", "anonim", "emp_login_xato", "xodim", "noto'g'ri parol")
                return self.json(200, {"ok": False})
            emp = row_to_emp(row)
            emp.pop("pass", None)
            audit(lg, emp.get("role") or "xodim", "emp_login", "xodim", emp.get("name") or "")
            return self.json(200, {"ok": True, "emp": emp})

        # ---------- Zal egalari (owner paneli) ----------
        def _owner_by_login(lg):
            if not lg:
                return None
            db = get_db()
            row = db.execute("SELECT * FROM halls WHERE lower(login)=lower(?) AND login<>''", (lg,)).fetchone()
            db.close()
            return row

        def _owner_pub(row):
            h = row_to_hall(row)
            h.pop("pass", None)
            h["details"] = _light_details(h.get("details") or {})
            return h

        if path == "/api/auth/owner/login" and self.command == "POST":
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                d = json.loads(raw.decode("utf-8"))
            except Exception:
                return self.json(400, {"error": "JSON noto'g'ri"})
            lg = str(d.get("login") or "").strip()
            pw = str(d.get("password") or "")
            row = _owner_by_login(lg)
            if row is None or (row["pass"] or "") != pw:
                audit(lg or "?", "anonim", "owner_login_xato", "zal", "noto'g'ri parol")
                return self.json(200, {"ok": False, "error": "Login yoki parol noto'g'ri"})
            if str(row["status"] or "active").lower() not in ("active", "faol"):
                audit(lg, "egasi", "owner_login_blok", "zal", "faol bo'lmagan hisob")
                return self.json(200, {"ok": False, "error": "Zal faol emas. Operator bilan bog'laning."})
            audit(lg, "egasi", "owner_login", "zal", row["name"] or "")
            return self.json(200, {"ok": True, "hall": _owner_pub(row)})

        # --- APK: telefon raqam bo'yicha zal egasini avtomatik aniqlash ---
        if path == "/api/auth/owner/by-phone" and self.command == "POST":
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                d = json.loads(raw.decode("utf-8"))
            except Exception:
                return self.json(400, {"error": "JSON noto'g'ri"})
            phone = norm_phone(str(d.get("phone") or ""))
            if not phone:
                return self.json(200, {"ok": False, "error": "Telefon raqam noto'g'ri"})
            db = get_db()
            row = db.execute(
                "SELECT * FROM halls WHERE phone=? AND phone NOT IN ('', '—')",
                (phone,)
            ).fetchone()
            if row is None:
                row = db.execute(
                    "SELECT * FROM halls WHERE phone LIKE ? AND phone NOT IN ('', '—')",
                    ("%" + phone[-9:] + "%",)
                ).fetchone()
            db.close()
            if row is None:
                return self.json(200, {"ok": False})
            if str(row["status"] or "active").lower() not in ("active", "faol"):
                return self.json(200, {"ok": False, "error": "Zal faol emas"})
            audit(phone, "egasi", "owner_phone_login", "zal", row["name"] or "")
            return self.json(200, {"ok": True, "hall": _owner_pub(row)})

        if path == "/api/owner/data" and self.command == "GET":
            row = _owner_by_login((self.headers.get("X-Elgaku-Login") or "").strip())
            if row is None:
                return self.json(403, {"error": "Avtorizatsiya talab qilinadi"})
            hall = row_to_hall(row)
            hall.pop("pass", None)
            hall["details"] = _light_details(hall.get("details") or {})
            hname = hall["name"] or ""
            db = get_db()
            try:
                tickets = [row_to_ticket(r) for r in db.execute(
                    "SELECT * FROM tickets WHERE hall=? ORDER BY id DESC", (hname,)).fetchall()]
            except Exception:
                tickets = []
            stats = {"total": 0, "yangi": 0, "jarayonda": 0, "hal": 0}
            for t in tickets:
                stats["total"] += 1
                st = t.get("status") or "yangi"
                stats[st] = stats.get(st, 0) + 1
            try:
                partners = db.execute("SELECT COUNT(*) FROM partners WHERE hall=?", (hname,)).fetchone()[0]
            except Exception:
                partners = 0
            db.close()
            return self.json(200, {"hall": hall, "tickets": tickets, "stats": stats, "partners": partners})

        if path == "/api/owner/hall" and self.command == "PUT":
            row = _owner_by_login((self.headers.get("X-Elgaku-Login") or "").strip())
            if row is None:
                return self.json(403, {"error": "Avtorizatsiya talab qilinadi"})
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                d = json.loads(raw.decode("utf-8"))
            except Exception:
                return self.json(400, {"error": "JSON noto'g'ri"})
            hid = row["id"]
            db = get_db()
            details = {}
            try:
                details = json.loads(row["details"] or "{}")
            except Exception:
                details = {}
            for k in ("city", "address", "hours", "desc", "phone2", "logo", "subtitle", "limit_abonements", "payme_id", "click_id"):
                if k in d:
                    details[k] = str(d[k] or "").strip()
            # Zal nomini o'zgartirish (egasi huquqi) — barcha bog'liq jadvallarda kaskad
            newname = (d.get("name") or "").strip()
            oldname = row["name"] or ""
            if newname and newname != oldname:
                db.execute("UPDATE halls SET name=? WHERE id=?", (newname, hid))
                try:
                    tbls = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
                    for t in tbls:
                        tn = t["name"]
                        cols = [c["name"] for c in db.execute("PRAGMA table_info(%s)" % tn).fetchall()]
                        if "hall" in cols and tn not in ("halls",):
                            db.execute("UPDATE %s SET hall=? WHERE hall=?" % tn, (newname, oldname))
                except Exception:
                    pass  # kaskad xatosi bloklamaydi — asosiy yozuv saqlanadi
            db.execute("UPDATE halls SET owner=?, phone=?, details=? WHERE id=?",
                       (str(d.get("owner") or row["owner"] or "—").strip() or "—",
                        str(d.get("phone") or row["phone"] or "—").strip() or "—",
                        json.dumps(details, ensure_ascii=False), hid))
            db.commit()
            r2 = db.execute("SELECT * FROM halls WHERE id=?", (hid,)).fetchone()
            db.close()
            hall = row_to_hall(r2)
            hall.pop("pass", None)
            hall["details"] = _light_details(hall.get("details") or {})
            return self.json(200, {"ok": True, "hall": hall})

        if path == "/api/owner/password" and self.command == "POST":
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                d = json.loads(raw.decode("utf-8"))
            except Exception:
                return self.json(400, {"error": "JSON noto'g'ri"})
            row = _owner_by_login(str(d.get("login") or "").strip())
            if row is None:
                return self.json(200, {"ok": False, "error": "Zal topilmadi"})
            if (row["pass"] or "") != str(d.get("oldpass") or ""):
                return self.json(200, {"ok": False, "error": "Hozirgi parol noto'g'ri"})
            npw = str(d.get("newpass") or "").strip()
            if len(npw) < 4:
                return self.json(200, {"ok": False, "error": "Yangi parol kamida 4 ta belgidan iborat bo'lsin"})
            db = get_db()
            db.execute("UPDATE halls SET pass=? WHERE id=?", (npw, row["id"]))
            db.commit()
            db.close()
            return self.json(200, {"ok": True})

        if path == "/api/profile" and self.command == "PUT":
            u = self.current_user()
            if u is None:
                return self.json(403, {"error": "Avtorizatsiya talab qilinadi"})
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                d = json.loads(raw.decode("utf-8"))
            except Exception:
                return self.json(400, {"error": "JSON noto'g'ri"})
            name = (d.get("name") or "").strip()
            nlogin = (d.get("login") or "").strip()
            oldp = d.get("oldpass") or ""
            np_ = d.get("pass") or ""
            photo = (d.get("photo") or "").strip()
            clearPhoto = bool(d.get("clearPhoto"))
            if not name or not nlogin:
                return self.json(400, {"error": "Ism va login majburiy"})
            db = get_db()
            if u.get("super"):
                s = self.super_settings()
                if oldp != (s["pass"] or ""):
                    db.close()
                    return self.json(403, {"error": "Hozirgi parol noto'g'ri"})
                other = db.execute("SELECT login FROM employees WHERE lower(login)=lower(?)", (nlogin,)).fetchone()
                if other and other["login"] != s["login"]:
                    db.close()
                    return self.json(409, {"error": "Bu login band"})
                old_login = s["login"]
                db.execute("UPDATE settings SET value=? WHERE key='super_login'", (nlogin,))
                db.execute("UPDATE settings SET value=? WHERE key='super_name'", (name,))
                if np_:
                    db.execute("UPDATE settings SET value=? WHERE key='super_pass'", (np_,))
                newphoto = photo if photo else ("" if clearPhoto else s["photo"])
                db.execute("UPDATE settings SET value=? WHERE key='super_photo'", (newphoto,))
                if nlogin.lower() != old_login.lower():
                    db.execute("UPDATE chat_online SET login=? WHERE login=?", (nlogin, old_login))
                db.commit()
                db.close()
                return self.json(200, {"ok": True, "login": nlogin, "name": name})
            row = db.execute("SELECT * FROM employees WHERE lower(login)=lower(?)", (u["login"],)).fetchone()
            if not row:
                db.close()
                return self.json(404, {"error": "Xodim topilmadi"})
            if oldp != (row["pass"] or ""):
                db.close()
                return self.json(403, {"error": "Hozirgi parol noto'g'ri"})
            if nlogin.lower() != u["login"].lower():
                other = db.execute("SELECT id FROM employees WHERE lower(login)=lower(?) AND id<>?", (nlogin, row["id"])).fetchone()
                if other:
                    db.close()
                    return self.json(409, {"error": "Bu login band"})
            newphoto = photo if photo else ("" if clearPhoto else (row["photo"] or ""))
            db.execute("UPDATE employees SET name=?, login=?, pass=?, photo=? WHERE id=?", (name, nlogin, np_ if np_ else row["pass"], newphoto, row["id"]))
            db.execute("UPDATE chat_online SET login=?, name=? WHERE login=?", (nlogin, name, u["login"]))
            db.commit()
            db.close()
            return self.json(200, {"ok": True, "login": nlogin, "name": name})

        if path == "/api/tickets" and self.command == "GET":
            cutoff = (datetime.datetime.now() - datetime.timedelta(days=30)).strftime("%Y-%m-%d %H:%M")
            db = get_db()
            db.execute("DELETE FROM tickets WHERE created < ?", (cutoff,))
            db.commit()
            u = self.current_user()
            # Zal egasi ham murojaatlarni ko'rishi mumkin (faqat o'z zali)
            lg = (self.headers.get("X-Elgaku-Login") or "").strip()
            owner_row = None
            if u is None and lg:
                owner_row = db.execute("SELECT * FROM halls WHERE lower(login)=lower(?)", (lg,)).fetchone()
            if u is None and owner_row is None:
                db.close()
                return self.json(403, {"error": "Avtorizatsiya talab qilinadi"})
            rows = db.execute("SELECT * FROM tickets ORDER BY id").fetchall()
            if self.is_ceo(u):
                out = [row_to_ticket(r) for r in rows]
            elif owner_row is not None:
                hname = owner_row["name"] or ""
                out = [row_to_ticket(r) for r in rows if (r["hall"] or "") == hname]
            else:
                name, login = u.get("name", ""), u.get("login", "")
                # Yangi (bo'sh) murojaatlar — operatorlarga ko'rinadi; o'ziniki; va bajarib bo'linganlar.
                out = [row_to_ticket(r) for r in rows
                       if r["status"] == "yangi" or (r["assignee"] or "") in (name, login) or r["status"] == "hal"]
            db.close()
            return self.json(200, out)

        if path == "/api/tickets" and self.command == "POST":
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                e = json.loads(raw.decode("utf-8"))
            except Exception:
                return self.json(400, {"error": "JSON noto'g'ri"})
            # Faqat tizim ichidagi rollar: zal egasi / operator / CEO.
            # Sayt va APK foydalanuvchilaridan murojaatlar qabul qilinmaydi.
            u = self.current_user()
            lg = (self.headers.get("X-Elgaku-Login") or "").strip()
            db = get_db()
            owner_row = None
            if u is None and lg:
                owner_row = db.execute("SELECT * FROM halls WHERE lower(login)=lower(?)", (lg,)).fetchone()
            if u is None and owner_row is None:
                db.close()
                return self.json(403, {"error": "Avtorizatsiya talab qilinadi — murojaat faqat zal egasi/operator yuboradi"})
            now = time.strftime("%Y-%m-%d %H:%M")
            n = db.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] + 1
            tid = e.get("tid") or ("T-%04d" % (1000 + n))
            # Manba: faqat zal egasi (operator/CEO ham 'zal' nomi bilan yozadi)
            src = e.get("source", "zal")
            if src not in ("zal", "egasi", "operator"):
                src = "zal"
            if src == "egasi":
                src = "zal"
            if owner_row is not None:
                # Egasi yozsa — zali avtomatik biriktiriladi
                e["hall"] = owner_row["name"] or e.get("hall", "")
                e["author"] = (e.get("author") or "").strip() or (owner_row["owner"] or owner_row["name"] or "Zal egasi")
                e["contact"] = (e.get("contact") or "").strip() or (owner_row["phone"] or "")
            hist = [{"t": now, "who": "Tizim", "note": "Zal egasi / operator orqali qabul qilindi"}]
            db.execute("INSERT INTO tickets(tid,source,type,author,contact,hall,subject,body,priority,status,assignee,history,chat,created,updated) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (tid, src, e.get("type", "savol"), e.get("author", "—"), e.get("contact", ""),
                        e.get("hall", ""), e.get("subject", ""), e.get("body", ""), e.get("priority", "normal"),
                        "yangi", "", json.dumps(hist, ensure_ascii=False), "[]", now, now))
            db.commit(); db.close()
            send_telegram("Yangi murojaat " + tid + ": " + (e.get("subject","")) + " (" + src + ")")
            return self.json(200, {"ok": True, "tid": tid})

        if path.startswith("/api/tickets/") and self.command == "PUT":
            tid = path.split("/api/tickets/")[1]
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                e = json.loads(raw.decode("utf-8"))
            except Exception:
                return self.json(400, {"error": "JSON noto'g'ri"})
            now = time.strftime("%Y-%m-%d %H:%M")
            db = get_db()
            row = db.execute("SELECT * FROM tickets WHERE tid=?", (tid,)).fetchone()
            if not row:
                db.close(); return self.json(404, {"error": "topilmadi"})
            u = self.current_user()
            if u is None:
                db.close(); return self.json(403, {"error": "Avtorizatsiya talab qilinadi"})
            ceo = self.is_ceo(u)
            name, login = u.get("name", ""), u.get("login", "")
            cur_owner = row["assignee"] or ""
            if ceo:
                new_assignee = e.get("assignee", cur_owner)
            elif e.get("claim") and cur_owner == "":
                # Operator bo'sh murojaatni o'zi oladi (qabul qiladi)
                new_assignee = name
            elif cur_owner in (name, login):
                if e.get("transfer"):
                    # Muammoni boshqa operatorga yuboradi
                    target = (e.get("assignee") or "").strip()
                    trow = db.execute("SELECT * FROM employees WHERE name=? OR lower(login)=lower(?)",
                                      (target, target)).fetchone()
                    if not trow:
                        db.close(); return self.json(400, {"error": "Operator topilmadi"})
                    new_assignee = trow["name"]
                else:
                    new_assignee = cur_owner
            else:
                db.close(); return self.json(409, {"error": "Murojaat boshqa operator tomonidan band"})
            db.execute("UPDATE tickets SET source=?,type=?,author=?,contact=?,hall=?,subject=?,body=?,priority=?,status=?,assignee=?,history=?,chat=?,followup=?,updated=? WHERE id=?",
                       (e.get("source", row["source"]), e.get("type", row["type"]), e.get("author", row["author"]),
                        e.get("contact", row["contact"]), e.get("hall", row["hall"]), e.get("subject", row["subject"]),
                        e.get("body", row["body"]), e.get("priority", row["priority"]), e.get("status", row["status"]),
                        new_assignee, json.dumps(e.get("history") or [], ensure_ascii=False),
                        json.dumps(e.get("chat") or [], ensure_ascii=False), e.get("followup", row["followup"] or ""),
                        now, row["id"]))
            if e.get("followup"):
                send_telegram("Qayta bog'lanish muddati: " + e.get("followup","") + " — " + (new_assignee or ""))
            db.commit(); db.close()
            return self.json(200, {"ok": True})

        if path.startswith("/api/tickets/") and self.command == "DELETE":
            tid = path.split("/api/tickets/")[1]
            u = self.current_user()
            if u is None:
                return self.json(403, {"error": "Avtorizatsiya talab qilinadi"})
            db = get_db()
            row = db.execute("SELECT * FROM tickets WHERE tid=?", (tid,)).fetchone()
            if not row:
                db.close(); return self.json(404, {"error": "topilmadi"})
            owner = row["assignee"] or ""
            if not (self.is_ceo(u) or owner in (u.get("name",""), u.get("login","")) or owner == ""):
                db.close(); return self.json(403, {"error": "Bu murojaatni o'chira olmaysiz"})
            db.execute("DELETE FROM tickets WHERE tid=?", (tid,)); db.commit(); db.close()
            return self.json(200, {"ok": True})

        # ---------- SMS xabarnoma ----------
        if path == "/api/sms/recipients" and self.command == "GET":
            u = self.current_user()
            if u is None:
                return self.json(403, {"error": "Avtorizatsiya talab qilinadi"})
            phones = sms_recipients()
            return self.json(200, {"count": len(phones), "phones": phones})

        if path == "/api/sms/send" and self.command == "POST":
            u = self.current_user()
            if u is None:
                return self.json(403, {"error": "Avtorizatsiya talab qilinadi"})
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                e = json.loads(raw.decode("utf-8"))
            except Exception:
                return self.json(400, {"error": "JSON noto'g'ri"})
            subject = (e.get("subject") or "").strip()
            text = (e.get("text") or "").strip()
            if not subject or not text:
                return self.json(400, {"error": "Mavzu va matn kerak"})
            phones = sms_recipients()
            if e.get("test"):
                phones = phones[:1] if phones else []
            now = time.strftime("%Y-%m-%d %H:%M")
            who = u.get("name") or u.get("login") or "—"
            db = get_db()
            sent = errs = 0
            for ph in phones:
                st = send_sms(ph, subject + "\n" + text)
                if st == "sent":
                    sent += 1
                elif st == "error":
                    errs += 1
                db.execute("INSERT INTO sms_log(phone, subject, text, status, operator, created) VALUES(?,?,?,?,?,?)",
                           (ph, subject, text, st, who, now))
            db.commit()
            db.close()
            send_telegram("SMS xabarnoma: " + subject + " — " + str(len(phones)) + " raqamga yuborildi")
            return self.json(200, {"ok": True, "total": len(phones), "sent": sent, "log": len(phones) - sent - errs, "errors": errs})

        if path == "/api/sms/log" and self.command == "GET":
            u = self.current_user()
            if u is None:
                return self.json(403, {"error": "Avtorizatsiya talab qilinadi"})
            db = get_db()
            rows = db.execute("SELECT * FROM sms_log ORDER BY id DESC LIMIT 100").fetchall()
            db.close()
            return self.json(200, [dict(r) for r in rows])

        if path == "/api/chat/online" and self.command == "GET":
            u = self.current_user()
            if u is None:
                return self.json(403, {"error": "Avtorizatsiya talab qilinadi"})
            now_e = int(time.time())
            db = get_db()
            db.execute("DELETE FROM chat_online WHERE last_seen < ?", (now_e - 120,))
            db.commit()
            online = [r["name"] for r in db.execute("SELECT * FROM chat_online WHERE last_seen >= ?", (now_e - 60,)).fetchall()]
            db.close()
            return self.json(200, {"online": online})

        # ---------- Operatorlar chat ----------
        if path == "/api/chat" and self.command == "GET":
            u = self.current_user()
            if u is None:
                return self.json(403, {"error": "Avtorizatsiya talab qilinadi"})
            chat_cleanup()
            now_e = int(time.time())
            db = get_db()
            db.execute("DELETE FROM chat_online WHERE last_seen < ?", (now_e - 120,))
            db.commit()
            _lg = (u.get("login") or "").lower()
            _nm = (u.get("name") or "").lower()
            rows = db.execute("SELECT * FROM chat_messages WHERE target='' OR lower(target)=? OR lower(target)=? OR lower(sender)=? OR lower(sender)=? ORDER BY id DESC LIMIT 100", (_lg, _nm, _lg, _nm)).fetchall()
            online = [r["name"] for r in db.execute("SELECT * FROM chat_online WHERE last_seen >= ?", (now_e - 60,)).fetchall()]
            db.close()
            msgs = [{"id": r["id"], "sender": r["sender"], "text": r["text"], "img": r["img"] or "", "fname": r["fname"] or "", "created": r["created"], "edited": r["edited"] if "edited" in r.keys() else 0, "sticker": r["sticker"] if "sticker" in r.keys() else "", "reply_to": r["reply_to"] if "reply_to" in r.keys() else 0, "dur": r["dur"] if "dur" in r.keys() else 0, "target": r["target"] if "target" in r.keys() else ""} for r in rows]
            msgs.reverse()
            return self.json(200, {"messages": msgs, "retention_days": CHAT_RETENTION_DAYS, "online": online})

        if path == "/api/chat/send" and self.command == "POST":
            u = self.current_user()
            if u is None:
                return self.json(403, {"error": "Avtorizatsiya talab qilinadi"})
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                e = json.loads(raw.decode("utf-8"))
            except Exception:
                return self.json(400, {"error": "JSON noto'g'ri"})
            text = (e.get("text") or "").strip()
            img = (e.get("img") or "").strip()
            fname = (e.get("fname") or "").strip()
            sticker = (e.get("sticker") or "").strip()
            reply_to = 0
            try:
                reply_to = int(e.get("reply_to") or 0)
            except Exception:
                reply_to = 0
            dur = 0
            try:
                dur = int(e.get("dur") or 0)
            except Exception:
                dur = 0
            if dur < 0 or dur > 600:
                dur = 0
            if sticker and not re.match(r"^ss\d{3}$", sticker):
                return self.json(400, {"error": "Stiker noto'g'ri"})
            if not text and not img and not sticker:
                return self.json(400, {"error": "Matn, fayl yoki stiker kerak"})
            if len(text) > 2000:
                return self.json(400, {"error": "Xabar juda uzun (2000 belgidan oshdi)"})
            if img:
                if not img.startswith("data:"):
                    return self.json(400, {"error": "Faqat fayl (data:) yuborish mumkin"})
                if len(img) > 8000000:
                    return self.json(400, {"error": "Fayl juda katta (5 MB dan oshdi)"})
            chat_cleanup()
            who = u.get("name") or u.get("login") or "—"
            now = time.strftime("%Y-%m-%d %H:%M")
            db = get_db()
            cur = db.execute("INSERT INTO chat_messages(sender, text, img, fname, sticker, reply_to, dur, created) VALUES(?,?,?,?,?,?,?,?)", (who, text, img, fname, sticker, reply_to, dur, now))
            db.commit()
            db.close()
            return self.json(200, {"ok": True, "id": cur.lastrowid, "created": now})

        if path == "/api/chat/heartbeat" and self.command == "POST":
            u = self.current_user()
            if u is None:
                return self.json(403, {"error": "Avtorizatsiya talab qilinadi"})
            now_e = int(time.time())
            db = get_db()
            db.execute("INSERT INTO chat_online(login, name, last_seen) VALUES(?,?,?) "
                       "ON CONFLICT(login) DO UPDATE SET name=excluded.name, last_seen=excluded.last_seen",
                       (u.get("login") or u.get("name") or "?", u.get("name") or u.get("login") or "?", now_e))
            db.commit()
            db.close()
            return self.json(200, {"ok": True, "t": now_e})

        if path.startswith("/api/chat/") and self.command == "PUT":
            try:
                cid = int(path.split("/")[-1])
            except ValueError:
                return self.json(400, {"error": "id noto'g'ri"})
            u = self.current_user()
            if u is None:
                return self.json(403, {"error": "Avtorizatsiya talab qilinadi"})
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                e = json.loads(raw.decode("utf-8"))
            except Exception:
                return self.json(400, {"error": "JSON noto'g'ri"})
            text = (e.get("text") or "").strip()
            if not text:
                return self.json(400, {"error": "Matn bo'sh bo'lishi mumkin emas"})
            if len(text) > 2000:
                return self.json(400, {"error": "Xabar juda uzun (2000 belgidan oshdi)"})
            db = get_db()
            row = db.execute("SELECT * FROM chat_messages WHERE id=?", (cid,)).fetchone()
            if not row:
                db.close(); return self.json(404, {"error": "topilmadi"})
            if not (self.is_ceo(u) or row["sender"] in (u.get("name", ""), u.get("login", ""))):
                db.close(); return self.json(403, {"error": "Faqat o'z xabaringizni tahrirlay olasiz"})
            db.execute("UPDATE chat_messages SET text=?, edited=1 WHERE id=?", (text, cid))
            db.commit(); db.close()
            return self.json(200, {"ok": True})

        if path.startswith("/api/chat/") and self.command == "DELETE":
            try:
                cid = int(path.split("/")[-1])
            except ValueError:
                return self.json(400, {"error": "id noto'g'ri"})
            u = self.current_user()
            if u is None:
                return self.json(403, {"error": "Avtorizatsiya talab qilinadi"})
            db = get_db()
            row = db.execute("SELECT * FROM chat_messages WHERE id=?", (cid,)).fetchone()
            if not row:
                db.close(); return self.json(404, {"error": "topilmadi"})
            # Har qanday operator istalgan xabarni hammadan o'chira oladi
            db.execute("DELETE FROM chat_messages WHERE id=?", (cid,))
            db.commit(); db.close()
            return self.json(200, {"ok": True})

        # ============ Zal egasi paneli: to'liq funksiyalar ============
        def _owner_row():
            return _owner_by_login((self.headers.get("X-Elgaku-Login") or "").strip())

        def _need_owner():
            r = _owner_row()
            if r is None:
                return None, self.json(403, {"error": "Avtorizatsiya talab qilinadi"})
            return r, None

        def _read_json():
            try:
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                return json.loads(raw.decode("utf-8")), None
            except Exception:
                return None, self.json(400, {"error": "JSON noto'g'ri"})
        # QR kod generatsiyasi (to'lov / check uchun)
        if path == "/api/owner/qr" and self.command == "GET":
            row, err = _need_owner()
            if err:
                return err
            q = urllib.parse.parse_qs(urlparse(self.path).query)
            text = (q.get("text") or [""])[0][:500]
            if not text:
                return self.json(400, {"error": "text bo'sh"})
            try:
                import qrcode
                img = qrcode.make(text)
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                b64 = base64.b64encode(buf.getvalue()).decode("ascii")
                return self.json(200, {"qr": "data:image/png;base64," + b64})
            except Exception:
                return self.json(500, {"error": "QR generatsiya xatosi"})


        if path == "/api/owner/password" and self.command == "PUT":
            row, err = _need_owner()
            if err:
                return err
            d, err = _read_json()
            if err:
                return err
            old = str(d.get("old") or "")
            new = str(d.get("new") or "").strip()
            if len(new) < 6:
                return self.json(400, {"error": "Yangi parol kamida 6 ta belgidan iborat bo'lsin"})
            if (row["pass"] or "") != old:
                audit(row["login"] or "", "egasi", "parol_xato", "zal", row["name"] or "")
                return self.json(400, {"error": "Eski parol noto'g'ri"})
            db = get_db()
            db.execute("UPDATE halls SET pass=? WHERE id=?", (new, row["id"]))
            db.commit()
            db.close()
            audit(row["login"] or "", "egasi", "parol_ozgartirildi", "zal", row["name"] or "")
            return self.json(200, {"ok": True})

        def _comm_rate(comm):
            try:
                s = str(comm or "0").replace("%", "").strip()
                if not s or s == "—":
                    return 0
                return float(s)
            except Exception:
                return 0

        # --- Dashboard: bugungi ko'rsatkichlar, grafiklar, jurnal ---
        if path == "/api/owner/dashboard" and self.command == "GET":
            row, err = _need_owner()
            if err:
                return err
            hname = row["name"] or ""
            today = time.strftime("%Y-%m-%d")
            db = get_db()
            tv = db.execute("SELECT * FROM hall_visits WHERE hall=? AND created LIKE ?",
                            (hname, today + "%")).fetchall()
            kirgan = sum(1 for v in tv if v["status"] == "kirgan")
            chiqqan = sum(1 for v in tv if v["status"] == "chiqqan")
            rad = sum(1 for v in tv if v["status"] == "rad")
            tp = db.execute("SELECT * FROM hall_payments WHERE hall=? AND created LIKE ?",
                            (hname, today + "%")).fetchall()
            rev_today = sum(float(p["amount"] or 0) for p in tp)
            nb = db.execute("SELECT * FROM bookings WHERE hall=? AND status='yangi'",
                            (hname,)).fetchall()
            from_dt = (datetime.datetime.now() - datetime.timedelta(days=13)).strftime("%Y-%m-%d")
            v14 = db.execute(
                "SELECT substr(created,1,10) d, COUNT(*) n FROM hall_visits WHERE hall=? AND created>=? GROUP BY d ORDER BY d",
                (hname, from_dt + " 00:00")).fetchall()
            day_rows = {}
            for i in range(14):
                day_rows[(datetime.datetime.now() - datetime.timedelta(days=13 - i)).strftime("%Y-%m-%d")] = 0
            for r in v14:
                day_rows[r["d"]] = r["n"]
            visits14 = [{"d": d, "n": day_rows[d]} for d in sorted(day_rows)]
            vh = db.execute(
                "SELECT substr(created,12,2) h, COUNT(*) n FROM hall_visits WHERE hall=? GROUP BY h ORDER BY n DESC LIMIT 6",
                (hname,)).fetchall()
            busy_hours = [{"h": r["h"], "n": r["n"]} for r in vh]
            ret = db.execute(
                "SELECT person, phone, COUNT(*) n, MAX(created) last FROM hall_visits WHERE hall=? AND status='kirgan' "
                "GROUP BY person, phone ORDER BY n DESC LIMIT 10", (hname,)).fetchall()
            retention = [{"person": r["person"], "phone": r["phone"], "n": r["n"], "last": r["last"]} for r in ret]
            rp = db.execute("SELECT * FROM hall_payments WHERE hall=? ORDER BY id DESC LIMIT 12",
                            (hname,)).fetchall()
            recent_payments = [dict(r) for r in rp]
            rv = db.execute("SELECT * FROM hall_visits WHERE hall=? ORDER BY id DESC LIMIT 12",
                            (hname,)).fetchall()
            recent_visits = [dict(r) for r in rv]
            allp = db.execute("SELECT SUM(CAST(amount AS REAL)) s FROM hall_payments WHERE hall=?",
                              (hname,)).fetchone()["s"] or 0
            rate = _comm_rate(row["commission"])
            comm = round(allp * rate / 100.0, 2)
            wd = db.execute("SELECT SUM(CAST(amount AS REAL)) s FROM withdrawals WHERE hall=? AND status='kutilmoqda'",
                            (hname,)).fetchone()["s"] or 0
            balance = {"total": round(allp, 2), "commission": comm, "net": round(allp - comm, 2),
                       "pending": round(wd, 2), "rate": rate}
            door = get_setting("door_" + hname, "qulf")
            # Oxirgi 14 kun daromadi (to'lovlar bo'yicha)
            rev14 = db.execute(
                "SELECT substr(created,1,10) d, SUM(CAST(amount AS REAL)) s FROM hall_payments "
                "WHERE hall=? AND created>=? GROUP BY d ORDER BY d",
                (hname, from_dt + " 00:00")).fetchall()
            revenue14 = []
            rev_day = dict(day_rows)
            for r in rev14:
                rev_day[r["d"]] = round(r["s"] or 0, 2)
            for d in sorted(rev_day):
                revenue14.append({"d": d, "s": rev_day[d]})
            # To'lov usullari bo'yicha tarkib
            meth = db.execute(
                "SELECT method, COUNT(*) n, SUM(CAST(amount AS REAL)) s FROM hall_payments "
                "WHERE hall=? GROUP BY method ORDER BY s DESC", (hname,)).fetchall()
            methods = [{"method": r["method"] or "—", "n": r["n"], "s": round(r["s"] or 0, 2)} for r in meth]
            # Eng ko'p sotilgan paketlar
            top = db.execute(
                "SELECT title, sold FROM packages WHERE hall=? AND sold>0 ORDER BY sold DESC LIMIT 5",
                (hname,)).fetchall()
            top_packages = [{"title": r["title"], "sold": r["sold"]} for r in top]
            # Abonementlar: faol / faol emas / muddati tugayotgan + limit nazorati
            mb = db.execute("SELECT * FROM memberships WHERE hall=?", (hname,)).fetchall()
            today_s = datetime.date.today().isoformat()
            end7 = (datetime.datetime.now() + datetime.timedelta(days=7)).strftime("%Y-%m-%d")
            active_memberships = 0
            inactive_memberships = 0
            expiring = 0
            for m in mb:
                st = m["status"]
                if st == "faol" and m["end"] and m["end"] < today_s:
                    st = "tugagan"
                if st == "faol" and m["type"] == "sessiyali" and (m["sessions_total"] or 0) > 0 and (m["sessions_used"] or 0) >= m["sessions_total"]:
                    st = "tugagan"
                if st == "faol":
                    active_memberships += 1
                    if m["end"] and m["end"] <= end7:
                        expiring += 1
                else:
                    inactive_memberships += 1
            limit_ab = 0
            try:
                limit_ab = int(json.loads(row["details"] or "{}").get("limit_abonements") or 0)
            except Exception:
                limit_ab = 0
            memberships_stat = {"active": active_memberships, "expiring": expiring,
                                "inactive": inactive_memberships, "total": len(mb),
                                "limit": limit_ab,
                                "over_limit": bool(limit_ab and active_memberships > limit_ab)}
            # --- Tezkor ogohlantirishlar (牛啦/微健 uslubi): tugash, sessiyalar, kontrakt, uxlab yotganlar ---
            end60 = (datetime.datetime.now() + datetime.timedelta(days=60)).strftime("%Y-%m-%d")
            end30 = (datetime.datetime.now() + datetime.timedelta(days=30)).strftime("%Y-%m-%d")
            month_ago = (datetime.datetime.now() - datetime.timedelta(days=30)).strftime("%Y-%m-%d")
            alerts = []
            for m in mb:
                st = m["status"]
                if st == "faol" and m["end"] and m["end"] < today_s:
                    st = "tugagan"
                if st == "faol" and m["type"] == "sessiyali" and (m["sessions_total"] or 0) > 0 and (m["sessions_used"] or 0) >= m["sessions_total"]:
                    st = "tugagan"
                if st != "faol":
                    continue
                left_days = None
                if m["end"]:
                    try:
                        left_days = (datetime.date.fromisoformat(m["end"]) - datetime.date.today()).days
                    except Exception:
                        left_days = None
                left_sessions = None
                if m["type"] == "sessiyali":
                    left_sessions = (m["sessions_total"] or 0) - (m["sessions_used"] or 0)
                if m["end"] and left_days is not None and left_days <= 60:
                    alerts.append({"kind": "muddat", "client": m["client"], "phone": m["phone"],
                                   "package": m["package"], "end": m["end"],
                                   "days_left": left_days, "sessions_left": None})
                elif m["type"] == "sessiyali" and left_sessions is not None and left_sessions <= 10:
                    alerts.append({"kind": "sessiya", "client": m["client"], "phone": m["phone"],
                                   "package": m["package"], "end": m["end"],
                                   "days_left": None, "sessions_left": left_sessions})
            # Shartnoma (1 yillik kontrakt) 30 kun ichida tugaydi
            for m in mb:
                if m["status"] == "faol" and m["contract_end"] and m["contract_end"] <= end30 and m["contract_end"] >= today_s:
                    alerts.append({"kind": "contract", "client": m["client"], "phone": m["phone"],
                                   "package": m["package"], "end": m["end"], "contract_end": m["contract_end"]})
            # "Uxlab yotgan" — faol abonementi bor, 30 kun davomida kelmagan
            last_vis = {}
            for v in db.execute("SELECT phone, MAX(created) last FROM hall_visits WHERE hall=? AND status='kirgan' AND phone!='' GROUP BY phone", (hname,)).fetchall():
                last_vis[v["phone"]] = v["last"]
            for m in mb:
                if m["status"] != "faol" or not m["phone"]:
                    continue
                lv = last_vis.get(m["phone"])
                if lv and lv[:10] < month_ago:
                    alerts.append({"kind": "sleep", "client": m["client"], "phone": m["phone"],
                                   "package": m["package"], "last_visit": lv[:10]})
            alerts = alerts[:20]
            # --- Qarzdorlar: faol abonement, lekin to'lov qaydi yo'q (牛啦 uslubi) ---
            paid = set()
            for p in db.execute("SELECT DISTINCT phone FROM hall_payments WHERE hall=? AND phone!=''", (hname,)).fetchall():
                paid.add(p["phone"])
            debtors = []
            for m in mb:
                st = m["status"]
                if st == "faol" and m["end"] and m["end"] < today_s:
                    st = "tugagan"
                if st == "faol" and m["type"] == "sessiyali" and (m["sessions_total"] or 0) > 0 and (m["sessions_used"] or 0) >= m["sessions_total"]:
                    st = "tugagan"
                if st == "faol" and m["phone"] and m["phone"] not in paid:
                    debtors.append({"client": m["client"], "phone": m["phone"],
                                    "package": m["package"], "end": m["end"]})
            debtors = debtors[:10]
            # --- Bugungi darslar + kelmaganlar (no-show) ---
            now_hhmm = time.strftime("%H:%M")
            today_lessons = db.execute("SELECT id, title, ctime FROM coach_schedule WHERE hall=? AND cdate=?",
                                       (hname, today_s)).fetchall()
            noshow = 0
            for lsn in today_lessons:
                if lsn["ctime"] and lsn["ctime"] <= now_hhmm:
                    cnt = db.execute("SELECT COALESCE(SUM(seats),0) FROM lesson_bookings WHERE hall=? AND lesson_id=? AND status='bron'",
                                     (hname, lsn["id"])).fetchone()[0]
                    noshow += (cnt or 0)
            if noshow:
                alerts.append({"kind": "noshow", "client": "", "phone": "", "package": "",
                               "count": noshow, "end": None})
            if debtors:
                alerts.append({"kind": "qarz", "client": "", "phone": "", "package": "",
                               "count": len(debtors), "end": None})
            # --- Eng ko'p dars qatnashgan a'zolar reytingi (牛啦 uslubi) ---
            top_members = []
            try:
                for t in db.execute("SELECT phone, person, COUNT(*) n, MAX(created) last "
                                     "FROM hall_visits WHERE hall=? AND status='kirgan' AND phone!='' "
                                     "GROUP BY phone ORDER BY n DESC LIMIT 10", (hname,)).fetchall():
                    nm = t["person"] or ""
                    if not nm:
                        c = db.execute("SELECT client FROM clients WHERE hall=? AND phone=?", (hname, t["phone"])).fetchone()
                        nm = c["client"] if c else (t["phone"] or "—")
                    top_members.append({"client": nm, "phone": t["phone"], "visits": t["n"],
                                        "last": (t["last"] or "")[:10]})
            except Exception:
                top_members = []
            alerts = alerts[:20]
            # --- "Bugun nima bo'ldi?" — qisqa avto-xulosa (AI yordamchi light) ---
            parts = []
            parts.append("Bugun %d mijoz keldi, daromad %.2f so'm" % (len(tv), rev_today))
            if nb:
                parts.append("%d ta yangi abonement" % len(nb))
            if alerts:
                alert_map = {"muddat": 0, "sessiya": 0, "contract": 0, "sleep": 0, "noshow": 0, "qarz": 0}
                for a in alerts:
                    alert_map[a["kind"]] = alert_map.get(a["kind"], 0) + 1
                if alert_map["muddat"]:
                    parts.append("%d ta karta 60 kun ichida tugaydi" % alert_map["muddat"])
                if alert_map["sessiya"]:
                    parts.append("%d ta mijozda 10 dan kam dars qoldi" % alert_map["sessiya"])
                if alert_map["sleep"]:
                    parts.append("%d ta mijoz 30 kun kelmagan" % alert_map["sleep"])
                if alert_map["noshow"]:
                    parts.append("%d kishi bugungi darsga kelmadi (bron qolgan)" % alert_map["noshow"])
                if alert_map["qarz"]:
                    parts.append("%d mijoz qarzdor (to'lov qaydi yo'q)" % alert_map["qarz"])
            over_limit_flag = bool(limit_ab and active_memberships > limit_ab)
            if over_limit_flag:
                parts.append("Diqqat: abonementlar limitidan oshdi!")
            db.close()
            return self.json(200, {
                "hall": {"id": row["id"], "name": hname, "owner": row["owner"], "phone": row["phone"],
                         "commission": row["commission"], "branch": row["branch"], "status": row["status"]},
                "today": {"now_inside": max(0, kirgan - chiqqan), "clients_today": len(tv),
                          "revenue_today": round(rev_today, 2), "new_bookings": len(nb),
                          "rad_attempts": rad, "lessons_today": len(today_lessons)},
                "visits14": visits14, "busy_hours": busy_hours, "retention": retention,
                "recent_payments": recent_payments, "recent_visits": recent_visits,
                "balance": balance, "door": door,
                "revenue14": revenue14, "methods": methods, "top_packages": top_packages,
                "memberships": memberships_stat,
                "alerts": alerts,
                "debtors": debtors,
                "top_members": top_members,
                "summary": ". ".join(parts) or "Bugun hali hech qanday harakat yo'q",
            })

        # --- Kirish-chiqish jurnali (yuzni tanish / nazorat simulyatsiyasi) ---
        if path == "/api/owner/visits" and self.command == "GET":
            row, err = _need_owner()
            if err:
                return err
            db = get_db()
            rows = db.execute("SELECT * FROM hall_visits WHERE hall=? ORDER BY id DESC LIMIT 100",
                              (row["name"] or "",)).fetchall()
            db.close()
            return self.json(200, [dict(r) for r in rows])

        if path == "/api/owner/visits" and self.command == "POST":
            row, err = _need_owner()
            if err:
                return err
            d, err = _read_json()
            if err:
                return err
            hname = row["name"] or ""
            db = get_db()
            db.execute("INSERT INTO hall_visits(hall,person,phone,kind,status,note,created) VALUES(?,?,?,?,?,?,?)",
                       (hname, str(d.get("person") or "—").strip(), str(d.get("phone") or "").strip(),
                        str(d.get("kind") or "mijoz").strip(), str(d.get("status") or "kirgan").strip(),
                        str(d.get("note") or "").strip(), time.strftime("%Y-%m-%d %H:%M")))
            db.commit()
            if str(d.get("status") or "") == "rad":
                send_telegram("ELGAKU egasi: to'lovsiz kirish urinishi — " + hname + " (" + str(d.get("person") or "—") + ")")
            db.close()
            return self.json(200, {"ok": True})

        if path == "/api/owner/device" and self.command in ("GET", "POST"):
            row, err = _need_owner()
            if err:
                return err
            hname = row["name"] or ""
            key = "door_" + hname
            if self.command == "POST":
                d, err = _read_json()
                if err:
                    return err
                set_setting(key, "ochiq" if str(d.get("state") or "") == "ochiq" else "qulf")
                return self.json(200, {"ok": True, "state": get_setting(key, "qulf")})
            return self.json(200, {"state": get_setting(key, "qulf")})

        # --- Bronlar va bandlik ---
        if path == "/api/owner/bookings" and self.command == "GET":
            row, err = _need_owner()
            if err:
                return err
            db = get_db()
            rows = db.execute("SELECT * FROM bookings WHERE hall=? ORDER BY id DESC", (row["name"] or "",)).fetchall()
            db.close()
            return self.json(200, [dict(r) for r in rows])

        if path == "/api/owner/bookings" and self.command == "POST":
            row, err = _need_owner()
            if err:
                return err
            d, err = _read_json()
            if err:
                return err
            db = get_db()
            db.execute("INSERT INTO bookings(hall,item,cdate,start,end,client,phone,status,note,created) "
                       "VALUES(?,?,?,?,?,?,?,?,?,?)",
                       (row["name"] or "", str(d.get("item") or "").strip(), str(d.get("cdate") or "").strip(),
                        str(d.get("start") or "").strip(), str(d.get("end") or "").strip(),
                        str(d.get("client") or "—").strip(), str(d.get("phone") or "").strip(),
                        "yangi", str(d.get("note") or "").strip(), time.strftime("%Y-%m-%d %H:%M")))
            db.commit()
            db.close()
            return self.json(200, {"ok": True})

        if path.startswith("/api/owner/bookings/") and self.command == "PUT":
            row, err = _need_owner()
            if err:
                return err
            try:
                bid = int(path.split("/")[-1])
            except ValueError:
                return self.json(400, {"error": "id noto'g'ri"})
            d, err = _read_json()
            if err:
                return err
            st = str(d.get("status") or "").strip()
            if st not in ("yangi", "tasdiqlangan", "rad", "kelgan", "bekor"):
                return self.json(400, {"error": "status noto'g'ri"})
            db = get_db()
            db.execute("UPDATE bookings SET status=?, note=? WHERE id=? AND hall=?",
                       (st, str(d.get("note") or "").strip(), bid, row["name"] or ""))
            db.commit()
            db.close()
            return self.json(200, {"ok": True})

        if path.startswith("/api/owner/bookings/") and self.command == "DELETE":
            row, err = _need_owner()
            if err:
                return err
            try:
                bid = int(path.split("/")[-1])
            except ValueError:
                return self.json(400, {"error": "id noto'g'ri"})
            db = get_db()
            db.execute("DELETE FROM bookings WHERE id=? AND hall=?", (bid, row["name"] or ""))
            db.commit()
            db.close()
            return self.json(200, {"ok": True})

        # --- Kupon va aksiyalar ---
        if path == "/api/owner/coupons" and self.command == "GET":
            row, err = _need_owner()
            if err:
                return err
            db = get_db()
            rows = db.execute("SELECT * FROM coupons WHERE hall=? ORDER BY id DESC", (row["name"] or "",)).fetchall()
            db.close()
            return self.json(200, [dict(r) for r in rows])

        if path == "/api/owner/coupons" and self.command == "POST":
            row, err = _need_owner()
            if err:
                return err
            d, err = _read_json()
            if err:
                return err
            db = get_db()
            db.execute("INSERT INTO coupons(hall,code,title,type,value,qty,used,valid_from,valid_to,active,created) "
                       "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                       (row["name"] or "", str(d.get("code") or "").strip(), str(d.get("title") or "Kupon").strip(),
                        str(d.get("type") or "percent").strip(), str(d.get("value") or "10").strip(),
                        int(d.get("qty") or 0), 0,
                        str(d.get("valid_from") or "").strip(), str(d.get("valid_to") or "").strip(),
                        1 if str(d.get("active", "1")) in ("1", "true", "True") else 0,
                        time.strftime("%Y-%m-%d %H:%M")))
            db.commit()
            db.close()
            return self.json(200, {"ok": True})

        if path.startswith("/api/owner/coupons/") and self.command == "PUT":
            row, err = _need_owner()
            if err:
                return err
            try:
                cid = int(path.split("/")[-1])
            except ValueError:
                return self.json(400, {"error": "id noto'g'ri"})
            d, err = _read_json()
            if err:
                return err
            db = get_db()
            if d.get("use"):
                db.execute("UPDATE coupons SET used=used+1 WHERE id=? AND hall=?", (cid, row["name"] or ""))
                send_telegram("ELGAKU egasi: kupon ishlatildi — " + (row["name"] or ""))
            else:
                db.execute("UPDATE coupons SET active=? WHERE id=? AND hall=?",
                           (1 if str(d.get("active", "1")) in ("1", "true", "True") else 0, cid, row["name"] or ""))
            db.commit()
            db.close()
            return self.json(200, {"ok": True})

        if path.startswith("/api/owner/coupons/") and self.command == "DELETE":
            row, err = _need_owner()
            if err:
                return err
            try:
                cid = int(path.split("/")[-1])
            except ValueError:
                return self.json(400, {"error": "id noto'g'ri"})
            db = get_db()
            db.execute("DELETE FROM coupons WHERE id=? AND hall=?", (cid, row["name"] or ""))
            db.commit()
            db.close()
            return self.json(200, {"ok": True})

        # --- E'lonlar paneli ---
        if path == "/api/owner/announcements" and self.command == "GET":
            row, err = _need_owner()
            if err:
                return err
            db = get_db()
            rows = db.execute("SELECT * FROM announcements WHERE hall=? ORDER BY id DESC", (row["name"] or "",)).fetchall()
            db.close()
            return self.json(200, [dict(r) for r in rows])

        if path == "/api/owner/announcements" and self.command == "POST":
            row, err = _need_owner()
            if err:
                return err
            d, err = _read_json()
            if err:
                return err
            db = get_db()
            db.execute("INSERT INTO announcements(hall,title,body,created) VALUES(?,?,?,?)",
                       (row["name"] or "", str(d.get("title") or "").strip(),
                        str(d.get("body") or "").strip(), time.strftime("%Y-%m-%d %H:%M")))
            db.commit()
            db.close()
            return self.json(200, {"ok": True})

        if path.startswith("/api/owner/announcements/") and self.command == "DELETE":
            row, err = _need_owner()
            if err:
                return err
            try:
                aid = int(path.split("/")[-1])
            except ValueError:
                return self.json(400, {"error": "id noto'g'ri"})
            db = get_db()
            db.execute("DELETE FROM announcements WHERE id=? AND hall=?", (aid, row["name"] or ""))
            db.commit()
            db.close()
            return self.json(200, {"ok": True})

        # --- Murabbiylar jadvali (guruh + individual) ---
        if path == "/api/owner/coaches" and self.command == "GET":
            row, err = _need_owner()
            if err:
                return err
            db = get_db()
            rows = db.execute("SELECT * FROM coach_schedule WHERE hall=? ORDER BY id DESC", (row["name"] or "",)).fetchall()
            db.close()
            return self.json(200, [dict(r) for r in rows])

        # --- Trener statistikasi: har bir murabbiyning darslari (oy / jami) — 牛啦 uslubi ---
        if path == "/api/owner/coach-stats" and self.command == "GET":
            row, err = _need_owner()
            if err:
                return err
            hname = row["name"] or ""
            month = time.strftime("%Y-%m")
            db = get_db()
            rows = db.execute("SELECT coach, title, kind, cdate FROM coach_schedule WHERE hall=?", (hname,)).fetchall()
            stats = {}
            for r in rows:
                c = (r["coach"] or "—").strip()
                if c not in stats:
                    stats[c] = {"coach": c, "oy": 0, "jami": 0, "guruh": 0, "individual": 0}
                stats[c]["jami"] += 1
                if (r["cdate"] or "")[:7] == month:
                    stats[c]["oy"] += 1
                if (r["kind"] or "guruh") == "guruh":
                    stats[c]["guruh"] += 1
                else:
                    stats[c]["individual"] += 1
            db.close()
            return self.json(200, sorted(stats.values(), key=lambda x: -x["oy"]))

        # --- Darslar + bronlar: jadvalni bron soni bilan qaytaradi (waitlist bilan) ---
        if path == "/api/owner/lessons" and self.command == "GET":
            row, err = _need_owner()
            if err:
                return err
            hname = row["name"] or ""
            db = get_db()
            rows = db.execute("SELECT * FROM coach_schedule WHERE hall=? ORDER BY cdate DESC, ctime DESC", (hname,)).fetchall()
            bks = db.execute("SELECT lesson_id, status, COUNT(*) n, SUM(seats) s FROM lesson_bookings WHERE hall=? GROUP BY lesson_id, status", (hname,)).fetchall()
            cnt = {}
            for b in bks:
                cnt.setdefault(b["lesson_id"], {})[b["status"]] = (b["s"] or b["n"] or 0)
            out = []
            for r in rows:
                d = dict(r)
                c = cnt.get(r["id"], {})
                d["bron"] = c.get("bron", 0)
                d["kelgan"] = c.get("kelgan", 0)
                d["kelmadi"] = c.get("kelmadi", 0)
                d["navbat"] = c.get("navbat", 0)
                out.append(d)
            db.close()
            return self.json(200, out)

        # --- Bron qo'yish (zal egasi mijoz nomidan bron qiladi — keksalar/mehmonlar uchun) ---
        if path == "/api/owner/lesson-bookings" and self.command == "POST":
            row, err = _need_owner()
            if err:
                return err
            d, err = _read_json()
            if err:
                return err
            hname = row["name"] or ""
            lesson_id = int(d.get("lesson_id") or 0)
            client = (d.get("client") or "").strip()
            if not lesson_id or not client:
                return self.json(400, {"error": "Dars va mijoz kerak"})
            db = get_db()
            les = db.execute("SELECT * FROM coach_schedule WHERE id=? AND hall=?", (lesson_id, hname)).fetchone()
            if not les:
                db.close()
                return self.json(404, {"error": "Dars topilmadi"})
            seats = max(1, int(d.get("seats") or 1))
            # guruh darsida o'rin to'lgan bo'lsa — navbatga yozamiz
            booked_now = 0
            for b in db.execute("SELECT status, SUM(seats) s FROM lesson_bookings WHERE hall=? AND lesson_id=? GROUP BY status", (hname, lesson_id)).fetchall():
                if b["status"] in ("bron", "kelgan"):
                    booked_now += (b["s"] or 0)
            cap = int(les["seats"] or 0)
            status = "bron"
            if cap and booked_now + seats > cap:
                status = "navbat"
            db.execute("INSERT INTO lesson_bookings(hall,lesson_id,client,phone,seats,status,note,created) VALUES(?,?,?,?,?,?,?,?)",
                       (hname, lesson_id, client, (d.get("phone") or "").strip(), seats, status,
                        (d.get("note") or "").strip(), time.strftime("%Y-%m-%d %H:%M")))
            db.execute("UPDATE coach_schedule SET booked=? WHERE id=?", (booked_now + seats, lesson_id))
            db.commit()
            db.close()
            return self.json(200, {"ok": True, "status": status})

        if path == "/api/owner/lesson-bookings" and self.command == "GET":
            row, err = _need_owner()
            if err:
                return err
            hname = row["name"] or ""
            lid = None
            q = self.path.split("?")[1] if "?" in self.path else ""
            for kv in q.split("&"):
                if kv.startswith("lesson_id="):
                    try:
                        lid = int(kv.split("=", 1)[1])
                    except ValueError:
                        lid = None
            db = get_db()
            if lid:
                rows = db.execute("SELECT b.*, c.title ltitle, c.cdate ldate, c.ctime ltime, c.coach lcoach "
                                  "FROM lesson_bookings b LEFT JOIN coach_schedule c ON c.id=b.lesson_id "
                                  "WHERE b.hall=? AND b.lesson_id=? ORDER BY b.id DESC", (hname, lid)).fetchall()
            else:
                rows = db.execute("SELECT b.*, c.title ltitle, c.cdate ldate, c.ctime ltime, c.coach lcoach "
                                  "FROM lesson_bookings b LEFT JOIN coach_schedule c ON c.id=b.lesson_id "
                                  "WHERE b.hall=? ORDER BY b.id DESC LIMIT 300", (hname,)).fetchall()
            db.close()
            return self.json(200, [dict(r) for r in rows])

        if path.startswith("/api/owner/lesson-bookings/") and self.command == "PUT":
            row, err = _need_owner()
            if err:
                return err
            try:
                bid = int(path.split("/")[-1])
            except ValueError:
                return self.json(400, {"error": "id noto'g'ri"})
            d, err = _read_json()
            if err:
                return err
            hname = row["name"] or ""
            st = (d.get("status") or "").strip()
            if st not in ("bron", "kelgan", "kelmadi", "bekor", "navbat"):
                return self.json(400, {"error": "holat noto'g'ri"})
            db = get_db()
            bk = db.execute("SELECT * FROM lesson_bookings WHERE id=? AND hall=?", (bid, hname)).fetchone()
            if not bk:
                db.close()
                return self.json(404, {"error": "bron topilmadi"})
            db.execute("UPDATE bookings SET status=? WHERE id=?", (st, bid))
            # darsning booked sonini qayta hisoblaymiz
            tot = 0
            for b in db.execute("SELECT status, SUM(seats) s FROM lesson_bookings WHERE hall=? AND lesson_id=? GROUP BY status",
                                (hname, bk["lesson_id"])).fetchall():
                if b["status"] in ("bron", "kelgan"):
                    tot += (b["s"] or 0)
            db.execute("UPDATE coach_schedule SET booked=? WHERE id=?", (tot, bk["lesson_id"]))
            db.commit()
            db.close()
            return self.json(200, {"ok": True})

        if path.startswith("/api/owner/lesson-bookings/") and self.command == "DELETE":
            row, err = _need_owner()
            if err:
                return err
            try:
                bid = int(path.split("/")[-1])
            except ValueError:
                return self.json(400, {"error": "id noto'g'ri"})
            hname = row["name"] or ""
            db = get_db()
            bk = db.execute("SELECT * FROM lesson_bookings WHERE id=? AND hall=?", (bid, hname)).fetchone()
            if bk:
                db.execute("DELETE FROM lesson_bookings WHERE id=?", (bid,))
                tot = 0
                for b in db.execute("SELECT status, SUM(seats) s FROM lesson_bookings WHERE hall=? AND lesson_id=? GROUP BY status",
                                    (hname, bk["lesson_id"])).fetchall():
                    if b["status"] in ("bron", "kelgan"):
                        tot += (b["s"] or 0)
                db.execute("UPDATE coach_schedule SET booked=? WHERE id=?", (tot, bk["lesson_id"]))
                db.commit()
            db.close()
            return self.json(200, {"ok": True})

        # --- Bron qoidalari (Sozlamalar): bekor qilish muddati, necha kun oldin bron qilish ---
        if path == "/api/owner/bron-rules" and self.command == "GET":
            row, err = _need_owner()
            if err:
                return err
            hname = row["name"] or ""
            db = get_db()
            rows = db.execute("SELECT k, v FROM hall_settings WHERE hall=?", (hname,)).fetchall()
            out = {r["k"]: r["v"] for r in rows}
            db.close()
            return self.json(200, {
                "cancel_before_hours": out.get("cancel_before_hours", "2"),
                "advance_days": out.get("advance_days", "7"),
                "allow_guest_book": out.get("allow_guest_book", "1"),
                "notify_days": out.get("notify_days", "60"),
                "notify_sessions": out.get("notify_sessions", "10"),
            })

        if path == "/api/owner/bron-rules" and self.command == "PUT":
            row, err = _need_owner()
            if err:
                return err
            d, err = _read_json()
            if err:
                return err
            hname = row["name"] or ""
            db = get_db()
            for k in ("cancel_before_hours", "advance_days", "allow_guest_book", "notify_days", "notify_sessions"):
                if k in d:
                    db.execute("DELETE FROM hall_settings WHERE hall=? AND k=?", (hname, k))
                    db.execute("INSERT INTO hall_settings(hall,k,v) VALUES(?,?,?)", (hname, k, str(d[k])))
            db.commit()
            db.close()
            return self.json(200, {"ok": True})

        # --- Xodimlar (staff): roli, maosh asosi, dars haqi, sotuv foizi ---
        if path == "/api/owner/staff" and self.command == "GET":
            row, err = _need_owner()
            if err:
                return err
            hname = row["name"] or ""
            db = get_db()
            rows = db.execute("SELECT * FROM staff WHERE hall=? ORDER BY id DESC", (hname,)).fetchall()
            db.close()
            return self.json(200, [dict(r) for r in rows])

        if path == "/api/owner/staff" and self.command == "POST":
            row, err = _need_owner()
            if err:
                return err
            d, err = _read_json()
            if err:
                return err
            hname = row["name"] or ""
            db = get_db()
            db.execute("INSERT INTO staff(hall,name,role,base_salary,per_lesson,sales_percent,active,created) VALUES(?,?,?,?,?,?,?,?)",
                       (hname, (d.get("name") or "").strip(), (d.get("role") or "trener").strip(),
                        int(d.get("base_salary") or 0), int(d.get("per_lesson") or 0),
                        int(d.get("sales_percent") or 0), str(d.get("active", "1")),
                        time.strftime("%Y-%m-%d %H:%M")))
            db.commit()
            db.close()
            return self.json(200, {"ok": True})

        if path.startswith("/api/owner/staff/") and self.command == "PUT":
            row, err = _need_owner()
            if err:
                return err
            try:
                sid = int(path.split("/")[-1])
            except ValueError:
                return self.json(400, {"error": "id noto'g'ri"})
            d, err = _read_json()
            if err:
                return err
            hname = row["name"] or ""
            db = get_db()
            cur = db.execute("SELECT * FROM staff WHERE id=? AND hall=?", (sid, hname)).fetchone()
            if not cur:
                db.close()
                return self.json(404, {"error": "xodim topilmadi"})
            db.execute("UPDATE staff SET name=?, role=?, base_salary=?, per_lesson=?, sales_percent=?, active=? WHERE id=?",
                       ((d.get("name") or cur["name"]).strip(), (d.get("role") or cur["role"]).strip(),
                        int(d.get("base_salary", cur["base_salary"])), int(d.get("per_lesson", cur["per_lesson"])),
                        int(d.get("sales_percent", cur["sales_percent"])), str(d.get("active", cur["active"])), sid))
            db.commit()
            db.close()
            return self.json(200, {"ok": True})

        if path.startswith("/api/owner/staff/") and self.command == "DELETE":
            row, err = _need_owner()
            if err:
                return err
            try:
                sid = int(path.split("/")[-1])
            except ValueError:
                return self.json(400, {"error": "id noto'g'ri"})
            hname = row["name"] or ""
            db = get_db()
            db.execute("DELETE FROM staff WHERE id=? AND hall=?", (sid, hname))
            db.commit()
            db.close()
            return self.json(200, {"ok": True})

        # --- Maosh avtomatik hisoblash (抖音 uslubi): asosiy + dars haqi + sotuv foizi ---
        if path == "/api/owner/staff-salaries" and self.command == "GET":
            row, err = _need_owner()
            if err:
                return err
            hname = row["name"] or ""
            month = time.strftime("%Y-%m")
            db = get_db()
            staff = db.execute("SELECT * FROM staff WHERE hall=?", (hname,)).fetchall()
            lessons = db.execute("SELECT coach, COUNT(*) n FROM coach_schedule WHERE hall=? AND cdate LIKE ? GROUP BY coach",
                                 (hname, month + "%")).fetchall()
            ln = {r["coach"]: r["n"] for r in lessons}
            rev = db.execute("SELECT SUM(amount) s FROM hall_payments WHERE hall=? AND created LIKE ?",
                             (hname, month + "%")).fetchone()
            monthly_rev = float(rev["s"] or 0)
            out = []
            for s in staff:
                cnt = ln.get(s["name"], 0)
                base = s["base_salary"] or 0
                per = s["per_lesson"] or 0
                pct = s["sales_percent"] or 0
                sales = round(monthly_rev * pct / 100.0, 2) if pct else 0
                total = base + per * cnt + sales
                out.append({"id": s["id"], "name": s["name"], "role": s["role"], "active": s["active"],
                            "oy_darslar": cnt, "asosiy": base, "dars_haqi": per * cnt,
                            "sotuv_foiz": sales, "jami": round(total, 2), "month": month})
            db.close()
            return self.json(200, {"month": month, "staff": out})

        # --- Marketing: kuponlar (chegirma / bepul dars / do'stga taklif) ---
        if path == "/api/owner/promo-coupons" and self.command == "GET":
            row, err = _need_owner()
            if err:
                return err
            hname = row["name"] or ""
            db = get_db()
            rows = db.execute("SELECT * FROM promo_coupons WHERE hall=? ORDER BY id DESC", (hname,)).fetchall()
            db.close()
            return self.json(200, [dict(r) for r in rows])

        if path == "/api/owner/promo-coupons" and self.command == "POST":
            row, err = _need_owner()
            if err:
                return err
            d, err = _read_json()
            if err:
                return err
            hname = row["name"] or ""
            code = (d.get("code") or "").strip().upper() or ("KUPON" + str(int(time.time()) % 100000))
            db = get_db()
            db.execute("INSERT INTO promo_coupons(hall,code,title,kind,amount,percent,active,created) VALUES(?,?,?,?,?,?,?,?)",
                       (hname, code, (d.get("title") or "").strip(), (d.get("kind") or "chegirma").strip(),
                        int(d.get("amount") or 0), int(d.get("percent") or 0), str(d.get("active", "1")),
                        time.strftime("%Y-%m-%d %H:%M")))
            db.commit()
            db.close()
            return self.json(200, {"ok": True, "code": code})

        if path.startswith("/api/owner/promo-coupons/") and self.command == "DELETE":
            row, err = _need_owner()
            if err:
                return err
            try:
                cid = int(path.split("/")[-1])
            except ValueError:
                return self.json(400, {"error": "id noto'g'ri"})
            hname = row["name"] or ""
            db = get_db()
            db.execute("DELETE FROM promo_coupons WHERE id=? AND hall=?", (cid, hname))
            db.commit()
            db.close()
            return self.json(200, {"ok": True})

        # --- Kuponni tekshirish (Meituan/Douyin hamkori yoki o'z kuponi) ---
        if path == "/api/owner/promo-coupons/check" and self.command == "POST":
            row, err = _need_owner()
            if err:
                return err
            d, err = _read_json()
            if err:
                return err
            code = (d.get("code") or "").strip().upper()
            hname = row["name"] or ""
            db = get_db()
            c = db.execute("SELECT * FROM promo_coupons WHERE hall=? AND code=?", (hname, code)).fetchone()
            db.close()
            if not c:
                return self.json(404, {"error": "Kupon topilmadi", "code": code})
            if c["active"] != "1":
                return self.json(403, {"error": "Kupon faol emas", "code": code})
            return self.json(200, {"ok": True, "title": c["title"], "kind": c["kind"],
                                   "amount": c["amount"], "percent": c["percent"], "code": code})

        # --- Tana o'lchovi tarixi (vazn/BMI/yog' foizi) — mijoz kartotekasida grafik (牛啦 uslubi) ---
        if path == "/api/owner/body" and self.command == "POST":
            row, err = _need_owner()
            if err:
                return err
            d, err = _read_json()
            if err:
                return err
            hname = row["name"] or ""
            phone = (d.get("phone") or "").strip()
            client = (d.get("client") or "").strip()
            if not phone and not client:
                return self.json(400, {"error": "Mijoz telefon yoki ismi kerak"})
            db = get_db()
            db.execute("INSERT INTO body_measurements(hall,client,phone,weight,bmi,fat,note,created) "
                       "VALUES(?,?,?,?,?,?,?,?)",
                       (hname, client, phone, float(d.get("weight") or 0), float(d.get("bmi") or 0),
                        float(d.get("fat") or 0), str(d.get("note") or "").strip(),
                        time.strftime("%Y-%m-%d %H:%M")))
            db.commit()
            db.close()
            return self.json(200, {"ok": True})

        if path == "/api/owner/body" and self.command == "GET":
            row, err = _need_owner()
            if err:
                return err
            hname = row["name"] or ""
            prm = dict(urllib.parse.parse_qsl(urlparse(self.path).query))
            phone = prm.get("phone", "")
            db = get_db()
            if phone:
                rows = db.execute("SELECT * FROM body_measurements WHERE hall=? AND phone=? ORDER BY id ASC LIMIT 60",
                                  (hname, phone)).fetchall()
            else:
                rows = db.execute("SELECT * FROM body_measurements WHERE hall=? ORDER BY id DESC LIMIT 60",
                                  (hname,)).fetchall()
            db.close()
            return self.json(200, [dict(r) for r in rows])

        if path == "/api/owner/coaches" and self.command == "POST":
            row, err = _need_owner()
            if err:
                return err
            d, err = _read_json()
            if err:
                return err
            db = get_db()
            db.execute("INSERT INTO coach_schedule(hall,coach,title,kind,cdate,ctime,seats,booked,price,created) "
                       "VALUES(?,?,?,?,?,?,?,?,?,?)",
                       (row["name"] or "", str(d.get("coach") or "").strip(), str(d.get("title") or "").strip(),
                        str(d.get("kind") or "guruh").strip(), str(d.get("cdate") or "").strip(),
                        str(d.get("ctime") or "").strip(), int(d.get("seats") or 0), 0,
                        str(d.get("price") or "").strip(), time.strftime("%Y-%m-%d %H:%M")))
            db.commit()
            db.close()
            return self.json(200, {"ok": True})

        if path.startswith("/api/owner/coaches/") and self.command == "DELETE":
            row, err = _need_owner()
            if err:
                return err
            try:
                cid = int(path.split("/")[-1])
            except ValueError:
                return self.json(400, {"error": "id noto'g'ri"})
            db = get_db()
            db.execute("DELETE FROM coach_schedule WHERE id=? AND hall=?", (cid, row["name"] or ""))
            db.commit()
            db.close()
            return self.json(200, {"ok": True})

        if path.startswith("/api/owner/coaches/") and self.command == "PUT":
            row, err = _need_owner()
            if err:
                return err
            try:
                cid = int(path.split("/")[-1])
            except ValueError:
                return self.json(400, {"error": "id noto'g'ri"})
            d, err = _read_json()
            if err:
                return err
            db = get_db()
            cur = db.execute("SELECT id FROM coach_schedule WHERE id=? AND hall=?", (cid, row["name"] or "")).fetchone()
            if not cur:
                db.close()
                return self.json(404, {"error": "mashg'ulot topilmadi"})
            db.execute("UPDATE coach_schedule SET coach=?, title=?, kind=?, cdate=?, ctime=?, seats=?, price=? WHERE id=? AND hall=?",
                       (str(d.get("coach") or "").strip(), str(d.get("title") or "").strip(),
                        str(d.get("kind") or "guruh").strip(), str(d.get("cdate") or "").strip(),
                        str(d.get("ctime") or "").strip(), int(d.get("seats") or 0),
                        str(d.get("price") or "").strip(), cid, row["name"] or ""))
            db.commit()
            db.close()
            return self.json(200, {"ok": True})

        # --- Mijozlar bazasi: qo'lda kiritilgan (tasdiqlash bilan) + avto (tashriflardan) ---
        if path == "/api/owner/clients" and self.command == "GET":
            row, err = _need_owner()
            if err:
                return err
            hname = row["name"] or ""
            db = get_db()
            today = datetime.date.today().isoformat()
            manual = db.execute("SELECT * FROM clients WHERE hall=? ORDER BY id DESC", (hname,)).fetchall()
            auto = db.execute(
                "SELECT person, phone, COUNT(*) n, MAX(created) last FROM hall_visits WHERE hall=? "
                "GROUP BY person, phone ORDER BY n DESC, last DESC", (hname,)).fetchall()
            paid = db.execute(
                "SELECT client, phone, SUM(CAST(amount AS REAL)) s FROM hall_payments WHERE hall=? "
                "GROUP BY client, phone", (hname,)).fetchall()
            paid_map = {}
            for p in paid:
                key = ((p["client"] or "").strip(), (p["phone"] or "").strip())
                paid_map[key] = round(p["s"] or 0, 2)
            ms_rows = db.execute("SELECT * FROM memberships WHERE hall=? ORDER BY id DESC", (hname,)).fetchall()
            def _attach(c_person, c_phone, base):
                base = dict(base)
                key = ((c_person or "").strip(), (c_phone or "").strip())
                base["total_paid"] = paid_map.get(key, 0)
                # Eng so'nggi (faol yoki oxirgi) abonement + shartnoma
                ms = None
                for m in ms_rows:
                    mk = ((m["client"] or "").strip(), (m["phone"] or "").strip())
                    if mk == key or (c_person and (m["client"] or "").strip() == (c_person or "").strip()):
                        ms = m
                        break
                if ms is None:
                    base["abonement"] = None
                    base["has_abonement"] = False
                    base["contract_end"] = ""
                    return base
                st = ms["status"]
                if st == "faol" and ms["end"] and ms["end"] < today:
                    st = "tugagan"
                if st == "faol" and ms["type"] == "sessiyali" and (ms["sessions_total"] or 0) > 0 and (ms["sessions_used"] or 0) >= ms["sessions_total"]:
                    st = "tugagan"
                days_left = None
                if st == "faol" and ms["end"]:
                    try:
                        days_left = (datetime.date.fromisoformat(ms["end"]) - datetime.date.today()).days
                    except Exception:
                        days_left = None
                base["abonement"] = {"id": ms["id"], "package": ms["package"] or "", "type": ms["type"],
                                     "end": ms["end"] or "", "status": st, "days_left": days_left,
                                     "sessions_total": ms["sessions_total"], "sessions_used": ms["sessions_used"],
                                     "price": ms["price"] or "0"}
                base["has_abonement"] = True
                base["contract_end"] = ms["contract_end"] or ""
                return base
            manual_phones = set()
            out = []
            for r in manual:
                key = ((r["person"] or "").strip(), (r["phone"] or "").strip())
                manual_phones.add(key)
                out.append(_attach(r["person"], r["phone"], {"id": r["id"], "person": r["person"], "phone": r["phone"],
                            "status": r["status"] or "yangi", "note": r["note"] or "",
                            "visits": 0, "points": 0,
                            "last": "", "manual": True, "created": r["created"] or ""}))
            # Avtomatik tashriflar — qo'lda kiritilmaganlari qo'shiladi
            seen_keys = set(manual_phones)
            for r in auto:
                key = ((r["person"] or "").strip(), (r["phone"] or "").strip())
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                out.append(_attach(r["person"], r["phone"], {"id": None, "person": r["person"], "phone": r["phone"],
                            "status": "tasdiqlangan", "note": "", "visits": r["n"],
                            "points": r["n"] * 10, "last": r["last"], "manual": False}))
            # Abonementi bor, lekin tashrifsiz va qo'lda kiritilmagan mijozlar ham ko'rinishi kerak
            for m in ms_rows:
                key = ((m["client"] or "").strip(), (m["phone"] or "").strip())
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                out.append(_attach(m["client"], m["phone"], {"id": None, "person": m["client"], "phone": m["phone"],
                            "status": "tasdiqlangan", "note": "", "visits": 0,
                            "points": 0, "last": "", "manual": False}))
            db.close()
            return self.json(200, out)

        if path == "/api/owner/clients" and self.command == "POST":
            row, err = _need_owner()
            if err:
                return err
            d, err = _read_json()
            if err:
                return err
            person = (d.get("person") or "").strip()
            phone = (d.get("phone") or "").strip()
            if not person:
                return self.json(400, {"error": "Ismni kiriting"})
            hname = row["name"] or ""
            db = get_db()
            dup = db.execute("SELECT id FROM clients WHERE hall=? AND lower(person)=? AND lower(phone)=?",
                             (hname, person.lower(), (phone or "").lower())).fetchone()
            if dup:
                db.close()
                return self.json(400, {"error": "Bunday mijoz allaqachon bor"})
            db.execute("INSERT INTO clients(hall,person,phone,status,note,created) VALUES(?,?,?,?,?,?)",
                       (hname, person, phone, str(d.get("status") or "yangi").strip(),
                        str(d.get("note") or "").strip(), time.strftime("%Y-%m-%d %H:%M")))
            db.commit()
            db.close()
            return self.json(200, {"ok": True})

        if path.startswith("/api/owner/clients/") and self.command == "PUT":
            row, err = _need_owner()
            if err:
                return err
            try:
                cid = int(path.split("/")[-1])
            except ValueError:
                return self.json(400, {"error": "id noto'g'ri"})
            d, err = _read_json()
            if err:
                return err
            db = get_db()
            cur = db.execute("SELECT id FROM clients WHERE id=? AND hall=?", (cid, row["name"] or "")).fetchone()
            if not cur:
                db.close()
                return self.json(404, {"error": "mijoz topilmadi"})
            person = (d.get("person") or "").strip() or "—"
            db.execute("UPDATE clients SET person=?, phone=?, status=?, note=? WHERE id=? AND hall=?",
                       (person, (d.get("phone") or "").strip(),
                        str(d.get("status") or "yangi").strip(),
                        str(d.get("note") or "").strip(), cid, row["name"] or ""))
            db.commit()
            db.close()
            return self.json(200, {"ok": True})

        if path.startswith("/api/owner/clients/") and self.command == "DELETE":
            row, err = _need_owner()
            if err:
                return err
            try:
                cid = int(path.split("/")[-1])
            except ValueError:
                return self.json(400, {"error": "id noto'g'ri"})
            db = get_db()
            db.execute("DELETE FROM clients WHERE id=? AND hall=?", (cid, row["name"] or ""))
            db.commit()
            db.close()
            return self.json(200, {"ok": True})

        # --- Mijoz 360 profili: tashriflar + to'lovlar tarixi (OpenTable uslubi) ---
        if path == "/api/owner/client" and self.command == "GET":
            row, err = _need_owner()
            if err:
                return err
            hname = row["name"] or ""
            q = urlparse(self.path)
            prm = dict(urllib.parse.parse_qsl(q.query))
            person = (prm.get("person") or "").strip()
            phone = (prm.get("phone") or "").strip()
            db = get_db()
            if person or phone:
                cond = "hall=?"
                args = [hname]
                if person and phone:
                    cond += " AND (person=? OR phone=?)"
                    args += [person, phone]
                elif person:
                    cond += " AND person=?"
                    args.append(person)
                else:
                    cond += " AND phone=?"
                    args.append(phone)
                visits = db.execute("SELECT * FROM hall_visits WHERE " + cond + " ORDER BY id DESC LIMIT 60", args).fetchall()
                paym = db.execute("SELECT * FROM hall_payments WHERE " + cond.replace("person", "client") + " ORDER BY id DESC LIMIT 60", args).fetchall()
                cl = db.execute("SELECT * FROM clients WHERE " + cond + " ORDER BY id DESC LIMIT 1", args).fetchone()
                mb = db.execute("SELECT * FROM memberships WHERE hall=? AND client=? ORDER BY id DESC LIMIT 1",
                                (hname, person or "")).fetchone()
            else:
                visits, paym, cl, mb = [], [], None, None
            db.close()
            return self.json(200, {"person": person, "phone": phone,
                                   "visits": [dict(v) for v in visits],
                                   "payments": [dict(p) for p in paym],
                                   "client": dict(cl) if cl else None,
                                   "membership": dict(mb) if mb else None})

        # --- Mijoz kartotekasi maydonlarini saqlash (teglar / vazn / eslatma) ---
        if path == "/api/owner/client-fields" and self.command == "POST":
            row, err = _need_owner()
            if err:
                return err
            d, err = _read_json()
            if err:
                return err
            hname = row["name"] or ""
            person = (d.get("person") or "").strip() or "—"
            phone = (d.get("phone") or "").strip()
            tag = (d.get("tag") or "").strip()
            weight = (d.get("weight") or "").strip()
            note = (d.get("note") or "").strip()
            db = get_db()
            cur = db.execute("SELECT id FROM clients WHERE hall=? AND person=? AND phone=?",
                             (hname, person, phone)).fetchone()
            if cur:
                db.execute("UPDATE clients SET tag=?, weight=?, note=? WHERE id=?", (tag, weight, note, cur["id"]))
            else:
                db.execute("INSERT INTO clients(hall,person,phone,status,tag,weight,note,created) VALUES(?,?,?,?,?,?,?,?)",
                           (hname, person, phone, "tasdiqlangan", tag, weight, note, time.strftime("%Y-%m-%d %H:%M")))
            db.commit()
            db.close()
            return self.json(200, {"ok": True})

        # --- Moliya: to'lovlar tarixi, balans, pul yechish, kassa ---
        if path == "/api/owner/finance" and self.command == "GET":
            row, err = _need_owner()
            if err:
                return err
            hname = row["name"] or ""
            db = get_db()
            ps = db.execute("SELECT * FROM hall_payments WHERE hall=? ORDER BY id DESC LIMIT 100", (hname,)).fetchall()
            ws = db.execute("SELECT * FROM withdrawals WHERE hall=? ORDER BY id DESC LIMIT 30", (hname,)).fetchall()
            tot = db.execute("SELECT SUM(CAST(amount AS REAL)) s FROM hall_payments WHERE hall=?", (hname,)).fetchone()["s"] or 0
            rate = _comm_rate(row["commission"])
            comm = round(tot * rate / 100.0, 2)
            kir = db.execute("SELECT COALESCE(SUM(amount),0) s FROM cashbox WHERE hall=? AND direction='kirim'", (hname,)).fetchone()["s"] or 0
            chiq = db.execute("SELECT COALESCE(SUM(amount),0) s FROM cashbox WHERE hall=? AND direction='chiqim'", (hname,)).fetchone()["s"] or 0
            today = time.strftime("%Y-%m-%d")
            t_in = db.execute("SELECT COALESCE(SUM(amount),0) s FROM cashbox WHERE hall=? AND direction='kirim' AND created LIKE ?",
                              (hname, today + "%")).fetchone()["s"] or 0
            t_out = db.execute("SELECT COALESCE(SUM(amount),0) s FROM cashbox WHERE hall=? AND direction='chiqim' AND created LIKE ?",
                               (hname, today + "%")).fetchone()["s"] or 0
            db.close()
            return self.json(200, {"payments": [dict(r) for r in ps], "withdrawals": [dict(r) for r in ws],
                                   "balance": {"total": round(tot, 2), "commission": comm,
                                               "net": round(tot - comm, 2), "rate": rate},
                                   "cash": {"jami_kirim": round(kir, 2), "jami_chiqim": round(chiq, 2),
                                            "kassadagi": round(kir - chiq, 2),
                                            "bugun_kirim": round(t_in, 2), "bugun_chiqim": round(t_out, 2)}})

        if path == "/api/owner/payments" and self.command == "POST":
            row, err = _need_owner()
            if err:
                return err
            d, err = _read_json()
            if err:
                return err
            db = get_db()
            db.execute("INSERT INTO hall_payments(hall,client,phone,amount,method,kind,note,status,created) "
                       "VALUES(?,?,?,?,?,?,?,?,?)",
                       (row["name"] or "", str(d.get("client") or "—").strip(), str(d.get("phone") or "").strip(),
                        str(d.get("amount") or "0").strip(), str(d.get("method") or "Naqd").strip(),
                        str(d.get("kind") or "obuna").strip(), str(d.get("note") or "").strip(),
                        "paid", time.strftime("%Y-%m-%d %H:%M")))
            # Kassa kirimi — pul oldi nazorati (har bir qabul auditda qoladi)
            try:
                db.execute("INSERT INTO cashbox(hall,direction,amount,method,note,actor,created) VALUES(?,?,?,?,?,?,?)",
                           (row["name"] or "", "kirim", float(d.get("amount") or 0), str(d.get("method") or "Naqd").strip(),
                            "To'lov qabul qilindi: " + str(d.get("client") or "—"), row["login"] or "",
                            time.strftime("%Y-%m-%d %H:%M")))
            except Exception:
                pass
            db.commit()
            db.close()
            send_telegram("ELGAKU egasi: yangi to'lov — " + (row["name"] or "") + " (" + str(d.get("amount") or "0") + ")")
            return self.json(200, {"ok": True})

        if path == "/api/owner/withdraw" and self.command == "POST":
            row, err = _need_owner()
            if err:
                return err
            d, err = _read_json()
            if err:
                return err
            amt = str(d.get("amount") or "").strip()
            try:
                amtf = float(amt)
            except Exception:
                return self.json(400, {"error": "summa noto'g'ri"})
            if amtf <= 0:
                return self.json(400, {"error": "summa 0 dan katta bo'lsin"})
            db = get_db()
            db.execute("INSERT INTO withdrawals(hall,amount,status,created,note) VALUES(?,?,?,?,?)",
                       (row["name"] or "", amt, "kutilmoqda", time.strftime("%Y-%m-%d %H:%M"),
                        str(d.get("note") or "").strip()))
            # Pul berdi nazorati — yechish chiqim sifatida kassada qayd etiladi
            try:
                db.execute("INSERT INTO cashbox(hall,direction,amount,method,note,actor,created) VALUES(?,?,?,?,?,?,?)",
                           (row["name"] or "", "chiqim", amtf, "Bank o'tkazma",
                            "Pul yechish so'rovi (kutilmoqda)", row["login"] or "",
                            time.strftime("%Y-%m-%d %H:%M")))
            except Exception:
                pass
            db.commit()
            db.close()
            send_telegram("ELGAKU: pul yechish so'rovi — " + (row["name"] or "") + " " + amt + " so'm")
            return self.json(200, {"ok": True})

        # --- Vending avtomat (assortiment + sotuv + inventar) ---
        if path == "/api/owner/products" and self.command == "GET":
            row, err = _need_owner()
            if err:
                return err
            db = get_db()
            rows = db.execute("SELECT * FROM vending_products WHERE hall=? ORDER BY id DESC", (row["name"] or "",)).fetchall()
            db.close()
            return self.json(200, [dict(r) for r in rows])

        if path == "/api/owner/products" and self.command == "POST":
            row, err = _need_owner()
            if err:
                return err
            d, err = _read_json()
            if err:
                return err
            db = get_db()
            db.execute("INSERT INTO vending_products(hall,name,price,stock,low_stock,active,created) "
                       "VALUES(?,?,?,?,?,?,?)",
                       (row["name"] or "", str(d.get("name") or "").strip(), str(d.get("price") or "0").strip(),
                        int(d.get("stock") or 0), int(d.get("low_stock") or 3),
                        1 if str(d.get("active", "1")) in ("1", "true", "True") else 0,
                        time.strftime("%Y-%m-%d %H:%M")))
            db.commit()
            db.close()
            return self.json(200, {"ok": True})

        if path.startswith("/api/owner/products/") and self.command == "PUT":
            row, err = _need_owner()
            if err:
                return err
            try:
                pid = int(path.split("/")[-1])
            except ValueError:
                return self.json(400, {"error": "id noto'g'ri"})
            d, err = _read_json()
            if err:
                return err
            db = get_db()
            if "stock" in d:
                db.execute("UPDATE vending_products SET stock=? WHERE id=? AND hall=?",
                           (int(d.get("stock") or 0), pid, row["name"] or ""))
            elif "active" in d:
                db.execute("UPDATE vending_products SET active=? WHERE id=? AND hall=?",
                           (1 if str(d.get("active")) in ("1", "true", "True") else 0, pid, row["name"] or ""))
            db.commit()
            db.close()
            return self.json(200, {"ok": True})

        if path.startswith("/api/owner/products/") and self.command == "DELETE":
            row, err = _need_owner()
            if err:
                return err
            try:
                pid = int(path.split("/")[-1])
            except ValueError:
                return self.json(400, {"error": "id noto'g'ri"})
            db = get_db()
            db.execute("DELETE FROM vending_products WHERE id=? AND hall=?", (pid, row["name"] or ""))
            db.commit()
            db.close()
            return self.json(200, {"ok": True})

        if path == "/api/owner/orders" and self.command == "POST":
            row, err = _need_owner()
            if err:
                return err
            d, err = _read_json()
            if err:
                return err
            hname = row["name"] or ""
            db = get_db()
            p = db.execute("SELECT * FROM vending_products WHERE id=? AND hall=?",
                           (int(d.get("product_id") or 0), hname)).fetchone()
            if not p:
                db.close()
                return self.json(404, {"error": "mahsulot topilmadi"})
            qty = max(1, int(d.get("qty") or 1))
            if (p["stock"] or 0) < qty:
                db.close()
                return self.json(400, {"error": "Zaxirada yetarli emas (qolgan: " + str(p["stock"] or 0) + ")"})
            amount = float(p["price"] or 0) * qty
            db.execute("UPDATE vending_products SET stock=stock-? WHERE id=?", (qty, p["id"]))
            db.execute("INSERT INTO vending_orders(hall,product,qty,amount,created) VALUES(?,?,?,?,?)",
                       (hname, p["name"], qty, round(amount, 2), time.strftime("%Y-%m-%d %H:%M")))
            db.execute("INSERT INTO hall_payments(hall,client,phone,amount,method,kind,note,status,created) "
                       "VALUES(?,?,?,?,?,?,?,?,?)",
                       (hname, "Avtomat", "", round(amount, 2), "Uzum", "vending", p["name"] + " x" + str(qty),
                        "paid", time.strftime("%Y-%m-%d %H:%M")))
            try:
                db.execute("INSERT INTO cashbox(hall,direction,amount,method,note,actor,created) VALUES(?,?,?,?,?,?,?)",
                           (hname, "kirim", round(amount, 2), "Uzum",
                            "Avtomat: " + p["name"] + " x" + str(qty), row["login"] or "",
                            time.strftime("%Y-%m-%d %H:%M")))
            except Exception:
                pass
            db.commit()
            db.close()
            return self.json(200, {"ok": True, "amount": round(amount, 2)})

        if path == "/api/owner/vending" and self.command == "GET":
            row, err = _need_owner()
            if err:
                return err
            hname = row["name"] or ""
            db = get_db()
            os_ = db.execute("SELECT * FROM vending_orders WHERE hall=? ORDER BY id DESC LIMIT 50", (hname,)).fetchall()
            today = time.strftime("%Y-%m-%d")
            rev = db.execute("SELECT SUM(CAST(amount AS REAL)) s FROM vending_orders WHERE hall=? AND created LIKE ?",
                             (hname, today + "%")).fetchone()["s"] or 0
            db.close()
            return self.json(200, {"orders": [dict(r) for r in os_], "today_revenue": round(rev, 2)})

        # --- Bildirishnomalar tasmasi (har bir harakat bitta bildirishnomada) ---
        if path == "/api/owner/events" and self.command == "GET":
            row, err = _need_owner()
            if err:
                return err
            hname = row["name"] or ""
            today = time.strftime("%Y-%m-%d")
            db = get_db()
            ev = []
            for b in db.execute("SELECT * FROM bookings WHERE hall=? AND status='yangi' ORDER BY id DESC LIMIT 15",
                                (hname,)).fetchall():
                ev.append({"type": "bron", "kind": "yangi_bron", "text": "Yangi bron: " + (b["item"] or "") + " — " + (b["client"] or "—"),
                           "time": b["created"], "id": b["id"], "action": True})
            for p in db.execute("SELECT * FROM hall_payments WHERE hall=? AND created LIKE ? ORDER BY id DESC LIMIT 10",
                                (hname, today + "%")).fetchall():
                ev.append({"type": "to'lov", "kind": "to'lov",
                           "text": "Yangi to'lov: " + (p["client"] or "") + " — " + (p["amount"] or "0") + " so'm (" + (p["method"] or "") + ")",
                           "time": p["created"], "id": p["id"], "action": False})
            for v in db.execute("SELECT * FROM hall_visits WHERE hall=? AND status='rad' ORDER BY id DESC LIMIT 10",
                                (hname,)).fetchall():
                ev.append({"type": "kirish", "kind": "to'lovsiz_kirish",
                           "text": "To'lovsiz kirish urinishi: " + (v["person"] or "—"),
                           "time": v["created"], "id": v["id"], "action": False})
            for cp in db.execute("SELECT * FROM coupons WHERE hall=? AND used>0 ORDER BY id DESC LIMIT 5", (hname,)).fetchall():
                ev.append({"type": "kupon", "kind": "kupon",
                           "text": "Kupon ishlatildi: " + (cp["code"] or "") + " (" + (cp["title"] or "") + ")",
                           "time": cp["created"], "id": cp["id"], "action": False})
            for o in db.execute("SELECT * FROM vending_orders WHERE hall=? AND created LIKE ? ORDER BY id DESC LIMIT 10",
                                (hname, today + "%")).fetchall():
                ev.append({"type": "vending", "kind": "vending",
                           "text": "Avtomat sotuvi: " + (o["product"] or "") + " x" + str(o["qty"]),
                           "time": o["created"], "id": o["id"], "action": False})
            # Paket sotuvlari (bugun)
            for p in db.execute("SELECT * FROM hall_payments WHERE hall=? AND kind='paket' AND created LIKE ? ORDER BY id DESC LIMIT 10",
                                (hname, today + "%")).fetchall():
                ev.append({"type": "paket", "kind": "paket",
                           "text": "Paket sotildi: " + (p["note"] or p["client"] or "") + " — " + (p["amount"] or "0") + " so'm",
                           "time": p["created"], "id": p["id"], "action": False})
            db.close()
            ev.sort(key=lambda x: x["time"] or "", reverse=True)
            return self.json(200, ev[:40])

        # --- Paketlar (Meituan uslubi: aksiya paketlari + necha marta sotilgani) ---
        if path == "/api/owner/packages" and self.command == "GET":
            row, err = _need_owner()
            if err:
                return err
            db = get_db()
            rows = db.execute("SELECT * FROM packages WHERE hall=? ORDER BY id DESC", (row["name"] or "",)).fetchall()
            db.close()
            return self.json(200, [dict(r) for r in rows])

        if path == "/api/owner/packages" and self.command == "POST":
            row, err = _need_owner()
            if err:
                return err
            d, err = _read_json()
            if err:
                return err
            db = get_db()
            db.execute("INSERT INTO packages(hall,title,desc,price,old_price,qty,sold,active,months,created) "
                       "VALUES(?,?,?,?,?,?,?,?,?,?)",
                       (row["name"] or "", str(d.get("title") or "").strip(), str(d.get("desc") or "").strip(),
                        str(d.get("price") or "0").strip(), str(d.get("old_price") or "").strip(),
                        int(d.get("qty") or 0), 0,
                        1 if str(d.get("active", "1")) in ("1", "true", "True") else 0,
                        int(d.get("months") or 1),
                        time.strftime("%Y-%m-%d %H:%M")))
            db.commit()
            db.close()
            return self.json(200, {"ok": True})

        if path.startswith("/api/owner/packages/") and self.command == "PUT":
            row, err = _need_owner()
            if err:
                return err
            try:
                pid = int(path.split("/")[-1])
            except ValueError:
                return self.json(400, {"error": "id noto'g'ri"})
            d, err = _read_json()
            if err:
                return err
            db = get_db()
            db.execute("UPDATE packages SET title=?, desc=?, price=?, old_price=?, qty=?, months=?, active=? WHERE id=? AND hall=?",
                       (str(d.get("title") or "").strip(), str(d.get("desc") or "").strip(),
                        str(d.get("price") or "0").strip(), str(d.get("old_price") or "").strip(),
                        int(d.get("qty") or 0), int(d.get("months") or 1),
                        1 if str(d.get("active", "1")) in ("1", "true", "True") else 0, pid, row["name"] or ""))
            db.commit()
            db.close()
            return self.json(200, {"ok": True})

        if path.startswith("/api/owner/packages/") and self.command == "DELETE":
            row, err = _need_owner()
            if err:
                return err
            try:
                pid = int(path.split("/")[-1])
            except ValueError:
                return self.json(400, {"error": "id noto'g'ri"})
            db = get_db()
            db.execute("DELETE FROM packages WHERE id=? AND hall=?", (pid, row["name"] or ""))
            db.commit()
            db.close()
            return self.json(200, {"ok": True})

        # Paket sotish / kassa orqali tasdiqlash (核销)
        if path.startswith("/api/owner/packages/") and path.endswith("/sell") and self.command == "POST":
            row, err = _need_owner()
            if err:
                return err
            try:
                pid = int(path.split("/")[-2])
            except ValueError:
                return self.json(400, {"error": "id noto'g'ri"})
            d, err = _read_json()
            if err:
                return err
            hname = row["name"] or ""
            db = get_db()
            p = db.execute("SELECT * FROM packages WHERE id=? AND hall=?", (pid, hname)).fetchone()
            if not p:
                db.close()
                return self.json(404, {"error": "paket topilmadi"})
            if (p["qty"] or 0) > 0 and (p["sold"] or 0) >= p["qty"]:
                db.close()
                return self.json(400, {"error": "Paket soni tugagan (sotilgan: " + str(p["sold"]) + "/" + str(p["qty"]) + ")"})
            amt = float(p["price"] or 0)
            db.execute("UPDATE packages SET sold=sold+1 WHERE id=?", (pid,))
            db.execute("INSERT INTO hall_payments(hall,client,phone,amount,method,kind,note,status,created) "
                       "VALUES(?,?,?,?,?,?,?,?,?)",
                       (hname, str(d.get("client") or "Paket: " + (p["title"] or "")).strip(),
                        str(d.get("phone") or "").strip(), round(amt, 2),
                        str(d.get("method") or "Naqd").strip(), "paket",
                        p["title"], "paid", time.strftime("%Y-%m-%d %H:%M")))
            try:
                db.execute("INSERT INTO cashbox(hall,direction,amount,method,note,actor,created) VALUES(?,?,?,?,?,?,?)",
                           (hname, "kirim", round(amt, 2), str(d.get("method") or "Naqd").strip(),
                            "Paket: " + (p["title"] or ""), row["login"] or "",
                            time.strftime("%Y-%m-%d %H:%M")))
            except Exception:
                pass
            db.commit()
            db.close()
            send_telegram("ELGAKU egasi: paket sotildi — " + hname + " (" + (p["title"] or "") + ")")
            return self.json(200, {"ok": True, "amount": round(amt, 2)})

        # --- Sharhlar va reyting (Dianping uslubi: ko'rish + javob berish) ---
        if path == "/api/owner/reviews" and self.command == "GET":
            row, err = _need_owner()
            if err:
                return err
            hname = row["name"] or ""
            db = get_db()
            rows = db.execute("SELECT * FROM hall_reviews WHERE hall=? ORDER BY id DESC", (hname,)).fetchall()
            avg = db.execute("SELECT AVG(rating) a, COUNT(*) c FROM hall_reviews WHERE hall=?", (hname,)).fetchone()
            db.close()
            return self.json(200, {"reviews": [dict(r) for r in rows],
                                   "avg": round(avg["a"] or 0, 1) if avg["c"] else 0,
                                   "count": avg["c"] or 0})

        if path.startswith("/api/owner/reviews/") and path.endswith("/reply") and self.command == "POST":
            row, err = _need_owner()
            if err:
                return err
            try:
                rid = int(path.split("/")[-2])
            except ValueError:
                return self.json(400, {"error": "id noto'g'ri"})
            d, err = _read_json()
            if err:
                return err
            db = get_db()
            db.execute("UPDATE hall_reviews SET reply=? WHERE id=? AND hall=?",
                       (str(d.get("reply") or "").strip(), rid, row["name"] or ""))
            db.commit()
            db.close()
            return self.json(200, {"ok": True})

        if path.startswith("/api/owner/reviews/") and self.command == "DELETE":
            row, err = _need_owner()
            if err:
                return err
            try:
                rid = int(path.split("/")[-1])
            except ValueError:
                return self.json(400, {"error": "id noto'g'ri"})
            db = get_db()
            db.execute("DELETE FROM hall_reviews WHERE id=? AND hall=?", (rid, row["name"] or ""))
            db.commit()
            db.close()
            return self.json(200, {"ok": True})

        # --- Abonementlar (乐刻/Mindbody uslubi: muddatli va sessiyali karta) ---
        if path == "/api/owner/memberships" and self.command == "GET":
            row, err = _need_owner()
            if err:
                return err
            hname = row["name"] or ""
            db = get_db()
            rows = db.execute("SELECT * FROM memberships WHERE hall=? ORDER BY id DESC", (hname,)).fetchall()
            today = datetime.date.today().isoformat()
            out = []
            for m in rows:
                st = m["status"]
                if st == "faol" and m["end"] and m["end"] < today:
                    st = "tugagan"
                if st == "faol" and m["type"] == "sessiyali" and (m["sessions_total"] or 0) > 0 and (m["sessions_used"] or 0) >= m["sessions_total"]:
                    st = "tugagan"
                d = dict(m); d["status_cur"] = st
                days_left = None
                if st == "faol" and m["end"]:
                    days_left = (datetime.date.fromisoformat(m["end"]) - datetime.date.today()).days
                    d["days_left"] = days_left
                out.append(d)
            db.close()
            return self.json(200, out)

        if path == "/api/owner/memberships" and self.command == "POST":
            row, err = _need_owner()
            if err:
                return err
            d, err = _read_json()
            if err:
                return err
            hname = row["name"] or ""
            db = get_db()
            start = str(d.get("start") or "").strip()
            contract_end = ""
            if start:
                try:
                    contract_end = (datetime.date.fromisoformat(start) + datetime.timedelta(days=365)).isoformat()
                except Exception:
                    contract_end = ""
            db.execute("INSERT INTO memberships(hall,client,phone,type,sessions_total,sessions_used,price,start,end,status,photo,passport,package,contract_end,created) "
                       "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (hname, str(d.get("client") or "—").strip(), str(d.get("phone") or "").strip(),
                        str(d.get("type") or "muddatli").strip(),
                        int(d.get("sessions_total") or 0), 0,
                        str(d.get("price") or "0").strip(),
                        start, str(d.get("end") or "").strip(),
                        "faol", str(d.get("photo") or "").strip(),
                        str(d.get("passport") or "").strip(), str(d.get("package") or "").strip(),
                        contract_end,
                        time.strftime("%Y-%m-%d %H:%M")))
            db.commit()
            db.close()
            send_telegram("ELGAKU egasi: yangi abonement — " + hname + " (" + (d.get("client") or "—") + ")")
            return self.json(200, {"ok": True})

        if path.startswith("/api/owner/memberships/") and path.endswith("/session") and self.command == "POST":
            row, err = _need_owner()
            if err:
                return err
            try:
                mid = int(path.split("/")[-2])
            except ValueError:
                return self.json(400, {"error": "id noto'g'ri"})
            hname = row["name"] or ""
            db = get_db()
            m = db.execute("SELECT * FROM memberships WHERE id=? AND hall=?", (mid, hname)).fetchone()
            if not m:
                db.close()
                return self.json(404, {"error": "abonement topilmadi"})
            if m["type"] == "sessiyali":
                if (m["sessions_used"] or 0) >= (m["sessions_total"] or 0):
                    db.close()
                    return self.json(400, {"error": "Sessiyalar tugagan"})
                db.execute("UPDATE memberships SET sessions_used=sessions_used+1 WHERE id=?", (mid,))
            db.execute("INSERT INTO hall_visits(hall,person,phone,kind,status,note,created) VALUES(?,?,?,?,?,?,?)",
                       (hname, m["client"], m["phone"] or "", "mijoz", "kirgan",
                        "Abonement orqali", time.strftime("%Y-%m-%d %H:%M")))
            db.commit()
            db.close()
            return self.json(200, {"ok": True})

        if path.startswith("/api/owner/memberships/") and self.command == "PUT":
            row, err = _need_owner()
            if err:
                return err
            try:
                mid = int(path.split("/")[-1])
            except ValueError:
                return self.json(400, {"error": "id noto'g'ri"})
            d, err = _read_json()
            if err:
                return err
            st = str(d.get("status") or "").strip()
            if st not in ("faol", "bekor", "tugagan"):
                return self.json(400, {"error": "status noto'g'ri"})
            db = get_db()
            db.execute("UPDATE memberships SET status=? WHERE id=? AND hall=?", (st, mid, row["name"] or ""))
            db.commit()
            db.close()
            return self.json(200, {"ok": True})

        if path.startswith("/api/owner/memberships/") and self.command == "DELETE":
            row, err = _need_owner()
            if err:
                return err
            try:
                mid = int(path.split("/")[-1])
            except ValueError:
                return self.json(400, {"error": "id noto'g'ri"})
            db = get_db()
            db.execute("DELETE FROM memberships WHERE id=? AND hall=?", (mid, row["name"] or ""))
            db.commit()
            db.close()
            return self.json(200, {"ok": True})

        # --- SMS/push (demo) ---
        if path == "/api/owner/sms" and self.command == "POST":
            row, err = _need_owner()
            if err:
                return err
            d, err = _read_json()
            if err:
                return err
            phones = str(d.get("phones") or "").strip()
            text = str(d.get("text") or "").strip()
            if not phones or not text:
                return self.json(400, {"error": "Telefon va matn kerak"})
            now = time.strftime("%Y-%m-%d %H:%M")
            db = get_db()
            for ph in [x.strip() for x in phones.replace(";", ",").split(",") if x.strip()]:
                db.execute("INSERT INTO sms_log(phone,subject,text,status,operator,created) VALUES(?,?,?,?,?,?)",
                           (ph, "Zal egasi bildirishnomasi", text, "demo_yuborildi", row["name"] or "", now))
            db.commit()
            db.close()
            return self.json(200, {"ok": True, "sent": len([x.strip() for x in phones.replace(";", ",").split(",") if x.strip()])})

        # =====================================================================
        # KASSA (pul oldi-berdi nazorati) — zal egasi / resepshn tomoni
        # =====================================================================
        if path == "/api/owner/cash" and self.command == "GET":
            row, err = _need_owner()
            if err:
                return err
            hname = row["name"] or ""
            db = get_db()
            kir = db.execute("SELECT COALESCE(SUM(amount),0) s FROM cashbox WHERE hall=? AND direction='kirim'", (hname,)).fetchone()["s"] or 0
            chiq = db.execute("SELECT COALESCE(SUM(amount),0) s FROM cashbox WHERE hall=? AND direction='chiqim'", (hname,)).fetchone()["s"] or 0
            today = time.strftime("%Y-%m-%d")
            t_in = db.execute("SELECT COALESCE(SUM(amount),0) s FROM cashbox WHERE hall=? AND direction='kirim' AND created LIKE ?",
                              (hname, today + "%")).fetchone()["s"] or 0
            t_out = db.execute("SELECT COALESCE(SUM(amount),0) s FROM cashbox WHERE hall=? AND direction='chiqim' AND created LIKE ?",
                               (hname, today + "%")).fetchone()["s"] or 0
            logs = db.execute("SELECT * FROM cashbox WHERE hall=? ORDER BY id DESC LIMIT 80", (hname,)).fetchall()
            db.close()
            return self.json(200, {
                "jami_kirim": round(kir, 2), "jami_chiqim": round(chiq, 2),
                "kassadagi": round(kir - chiq, 2),
                "bugun_kirim": round(t_in, 2), "bugun_chiqim": round(t_out, 2),
                "logs": [dict(r) for r in logs]})

        if path == "/api/owner/cash" and self.command == "POST":
            row, err = _need_owner()
            if err:
                return err
            d, err = _read_json()
            if err:
                return err
            direction = str(d.get("direction") or "kirim").strip()
            if direction not in ("kirim", "chiqim"):
                return self.json(400, {"error": "yo'nalish noto'g'ri"})
            try:
                amt = float(d.get("amount") or 0)
            except Exception:
                return self.json(400, {"error": "summa noto'g'ri"})
            if amt <= 0:
                return self.json(400, {"error": "summa 0 dan katta bo'lsin"})
            hname = row["name"] or ""
            db = get_db()
            if direction == "chiqim":
                have = db.execute("SELECT COALESCE(SUM(CASE WHEN direction='kirim' THEN amount ELSE -amount END),0) s FROM cashbox WHERE hall=?",
                                  (hname,)).fetchone()["s"] or 0
                if have < amt:
                    db.close()
                    return self.json(400, {"error": "Kassada yetarli pul yo'q (mavjud: " + str(round(have, 2)) + " so'm)"})
            db.execute("INSERT INTO cashbox(hall,direction,amount,method,note,actor,created) VALUES(?,?,?,?,?,?,?)",
                       (hname, direction, amt, str(d.get("method") or "Naqd").strip(),
                        str(d.get("note") or "").strip(), row["login"] or "",
                        time.strftime("%Y-%m-%d %H:%M")))
            db.commit()
            db.close()
            send_telegram("ELGAKU kassa: " + direction + " " + str(amt) + " so'm — " + hname)
            return self.json(200, {"ok": True})

        if path == "/api/owner/cash/close" and self.command == "POST":
            row, err = _need_owner()
            if err:
                return err
            d, err = _read_json()
            if err:
                return err
            hname = row["name"] or ""
            today = time.strftime("%Y-%m-%d")
            db = get_db()
            t_in = db.execute("SELECT COALESCE(SUM(amount),0) s FROM cashbox WHERE hall=? AND direction='kirim' AND created LIKE ?",
                              (hname, today + "%")).fetchone()["s"] or 0
            t_out = db.execute("SELECT COALESCE(SUM(amount),0) s FROM cashbox WHERE hall=? AND direction='chiqim' AND created LIKE ?",
                               (hname, today + "%")).fetchone()["s"] or 0
            db.execute("INSERT INTO cashbox(hall,direction,amount,method,note,actor,created) VALUES(?,?,?,?,?,?,?)",
                       (hname, "chiqim", 0, "Smena", "SMENA YOPISH — kirim: " + str(round(t_in, 2)) + ", chiqim: " + str(round(t_out, 2)) +
                        " (" + str(d.get("note") or "") + ")", row["login"] or "",
                        time.strftime("%Y-%m-%d %H:%M")))
            db.commit()
            db.close()
            return self.json(200, {"ok": True, "bugun_kirim": round(t_in, 2), "bugun_chiqim": round(t_out, 2),
                                   "farq": round(t_in - t_out, 2)})

        # =====================================================================
        # OPERATOR — barcha zallar bo'yicha pul nazorati (komissiya va to'lovlar)
        # =====================================================================
        def _need_op():
            u = self.current_user()
            if not u:
                return None, self.json(403, {"error": "Kirish taqiqlangan"})
            if not (u.get("super") or u.get("role") in ("CEO", "Operator")):
                return None, self.json(403, {"error": "Faqat operator huquqi"})
            return u, None

        if path == "/api/operator/cash" and self.command == "GET":
            u, err = _need_op()
            if err:
                return err
            db = get_db()
            rows = db.execute("SELECT c.*, h.name hall_name, h.type hall_type, h.login hall_login FROM cashbox c "
                              "LEFT JOIN halls h ON h.name=c.hall ORDER BY c.id DESC LIMIT 300").fetchall()
            per_hall = db.execute(
                "SELECT c.hall, h.type hall_type, h.login hall_login, "
                "COALESCE(SUM(CASE WHEN c.direction='kirim' THEN c.amount ELSE 0 END),0) kirim, "
                "COALESCE(SUM(CASE WHEN c.direction='chiqim' THEN c.amount ELSE 0 END),0) chiqim "
                "FROM cashbox c LEFT JOIN halls h ON h.name=c.hall GROUP BY c.hall ORDER BY kirim DESC").fetchall()
            db.close()
            return self.json(200, {"logs": [dict(r) for r in rows],
                                   "halls": [dict(r) for r in per_hall]})

        if path == "/api/operator/hall-payments" and self.command == "GET":
            u, err = _need_op()
            if err:
                return err
            db = get_db()
            rows = db.execute("SELECT p.*, h.type hall_type, h.login hall_login FROM hall_payments p "
                              "LEFT JOIN halls h ON h.name=p.hall ORDER BY p.id DESC LIMIT 400").fetchall()
            db.close()
            return self.json(200, [dict(r) for r in rows])

        if path.startswith("/api/operator/hall-payments/") and self.command == "PUT":
            u, err = _need_op()
            if err:
                return err
            try:
                pid = int(path.split("/")[-1])
            except ValueError:
                return self.json(400, {"error": "id noto'g'ri"})
            d, err = _read_json()
            if err:
                return err
            st = str(d.get("status") or "").strip()
            db = get_db()
            db.execute("UPDATE hall_payments SET status=? WHERE id=?", (st, pid))
            db.commit()
            db.close()
            audit(u.get("login") or "", u.get("role") or "CEO", "to'lov_holati", "hall_payments#" + str(pid), st)
            return self.json(200, {"ok": True})

        if path == "/api/operator/withdrawals" and self.command == "GET":
            u, err = _need_op()
            if err:
                return err
            db = get_db()
            rows = db.execute("SELECT w.*, h.type hall_type, h.login hall_login FROM withdrawals w "
                              "LEFT JOIN halls h ON h.name=w.hall ORDER BY w.id DESC LIMIT 200").fetchall()
            db.close()
            return self.json(200, [dict(r) for r in rows])

        if path.startswith("/api/operator/withdrawals/") and self.command == "PUT":
            u, err = _need_op()
            if err:
                return err
            try:
                wid = int(path.split("/")[-1])
            except ValueError:
                return self.json(400, {"error": "id noto'g'ri"})
            d, err = _read_json()
            if err:
                return err
            st = str(d.get("status") or "").strip()
            if st not in ("tasdiqlangan", "rad"):
                return self.json(400, {"error": "holat noto'g'ri"})
            db = get_db()
            w = db.execute("SELECT * FROM withdrawals WHERE id=?", (wid,)).fetchone()
            if not w:
                db.close()
                return self.json(404, {"error": "topilmadi"})
            db.execute("UPDATE withdrawals SET status=?, note=COALESCE(note,'') || ' | Operator: ' || ? WHERE id=?",
                       (st, str(d.get("note") or "").strip(), wid))
            db.commit()
            db.close()
            audit(u.get("login") or "", u.get("role") or "CEO", "yechish_" + st, "withdrawals#" + str(wid),
                  (w["hall"] or "") + " " + str(w["amount"]) + " so'm")
            send_telegram("ELGAKU: yechish " + st + " — " + (w["hall"] or "") + " " + str(w["amount"]) + " so'm")
            return self.json(200, {"ok": True})

        if path == "/api/operator/cash-pay" and self.command == "POST":
            # Operator tomonidan naqd to'lovni belgilash (Komissiya bo'limidan)
            # Bir vaqtning o'zida: hall_payments (TO'LANDI) + kassa kirimi — pul nazorati bilan sinxron
            u, err = _need_op()
            if err:
                return err
            d, err = _read_json()
            if err:
                return err
            hall = str(d.get("hall") or "").strip()
            amount = float(d.get("amount") or 0)
            if not hall or amount <= 0:
                return self.json(400, {"error": "Zal va summa kerak"})
            db = get_db()
            h = db.execute("SELECT * FROM halls WHERE lower(name)=lower(?)", (hall,)).fetchone()
            if h is None:
                db.close()
                return self.json(404, {"error": "zal topilmadi"})
            now = time.strftime("%Y-%m-%d %H:%M")
            db.execute("INSERT INTO hall_payments(hall,client,phone,amount,method,kind,note,status,created) "
                       "VALUES(?,?,?,?,?,?,?,?,?)",
                       (h["name"] or "", str(d.get("client") or "—").strip(), str(d.get("phone") or "").strip(),
                        str(amount), str(d.get("method") or "Naqd").strip(),
                        str(d.get("kind") or "obuna").strip(), str(d.get("note") or "").strip(),
                        "paid", now))
            db.execute("INSERT INTO cashbox(hall,direction,amount,method,note,actor,created) VALUES(?,?,?,?,?,?,?)",
                       (h["name"] or "", "kirim", amount, str(d.get("method") or "Naqd").strip(),
                        "Operator qabul qildi: " + str(d.get("client") or "—") + " (Komissiya bo'limi)",
                        (u.get("login") or "") + " (operator)", now))
            db.commit()
            db.close()
            audit(u.get("login") or "", u.get("role") or "CEO", "naqd_tolov", "hall_payments+" + (h["name"] or ""),
                  str(amount) + " so'm " + str(d.get("method") or "Naqd"))
            send_telegram("ELGAKU operator: naqd to'lov — " + (h["name"] or "") + " " + str(amount) + " so'm")
            return self.json(200, {"ok": True})

        if path == "/api/operator/reconcile" and self.command == "GET":
            u, err = _need_op()
            if err:
                return err
            db = get_db()
            today = time.strftime("%Y-%m-%d")
            rows = db.execute(
                "SELECT h.name hall, h.type hall_type, "
                "COALESCE((SELECT SUM(CAST(p.amount AS REAL)) FROM hall_payments p WHERE p.hall=h.name AND p.created LIKE ?),0) bugun, "
                "COALESCE((SELECT SUM(CAST(p.amount AS REAL)) FROM hall_payments p WHERE p.hall=h.name),0) jami, "
                "COALESCE((SELECT COUNT(*) FROM hall_payments p WHERE p.hall=h.name AND p.created LIKE ?),0) soni, "
                "COALESCE((SELECT SUM(CASE WHEN c.direction='kirim' THEN c.amount ELSE -c.amount END) FROM cashbox c WHERE c.hall=h.name),0) kassa, "
                "COALESCE((SELECT COUNT(*) FROM withdrawals w WHERE w.hall=h.name AND w.status='kutilmoqda'),0) kutilayotgan "
                "FROM halls h WHERE h.status='active' ORDER BY bugun DESC",
                (today + "%", today + "%")).fetchall()
            by_method = db.execute(
                "SELECT method, COUNT(*) n, SUM(CAST(amount AS REAL)) s FROM hall_payments WHERE created LIKE ? GROUP BY method ORDER BY s DESC",
                (today + "%",)).fetchall()
            db.close()
            return self.json(200, {"halls": [dict(r) for r in rows],
                                   "by_method": [dict(r) for r in by_method]})

        if path == "/api/operator/packages" and self.command == "GET":
            u, err = _need_op()
            if err:
                return err
            db = get_db()
            rows = db.execute("SELECT p.*, h.type hall_type, h.login hall_login FROM packages p "
                              "LEFT JOIN halls h ON h.name=p.hall ORDER BY p.sold DESC LIMIT 200").fetchall()
            db.close()
            return self.json(200, [dict(r) for r in rows])

        if path == "/api/operator/reviews" and self.command == "GET":
            u, err = _need_op()
            if err:
                return err
            db = get_db()
            rows = db.execute("SELECT r.*, h.type hall_type, h.login hall_login FROM hall_reviews r "
                              "LEFT JOIN halls h ON h.name=r.hall ORDER BY r.id DESC LIMIT 200").fetchall()
            db.close()
            return self.json(200, [dict(r) for r in rows])

        if path == "/api/operator/memberships" and self.command == "GET":
            u, err = _need_op()
            if err:
                return err
            db = get_db()
            rows = db.execute("SELECT m.*, h.type hall_type, h.login hall_login FROM memberships m "
                              "LEFT JOIN halls h ON h.name=m.hall ORDER BY m.id DESC LIMIT 200").fetchall()
            db.close()
            return self.json(200, [dict(r) for r in rows])

        # =====================================================================
        # XAVFSIZLIK — audit jurnali, hodisalar, zaxiralar, parollar
        # =====================================================================
        if path == "/api/operator/audit" and self.command == "GET":
            u, err = _need_op()
            if err:
                return err
            db = get_db()
            rows = db.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 300").fetchall()
            att = db.execute("SELECT * FROM login_attempts ORDER BY updated DESC LIMIT 100").fetchall()
            db.close()
            return self.json(200, {"log": [dict(r) for r in rows], "attempts": [dict(r) for r in att]})

        if path == "/api/operator/backup" and self.command == "GET":
            u, err = _need_op()
            if err:
                return err
            out = []
            try:
                if os.path.isdir(BACKUP_DIR):
                    for f in sorted(os.listdir(BACKUP_DIR), reverse=True):
                        if f.startswith("elgaku_") and f.endswith(".db"):
                            p = os.path.join(BACKUP_DIR, f)
                            out.append({"name": f, "size": os.path.getsize(p),
                                        "time": time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(p)))})
            except Exception:
                pass
            return self.json(200, out)

        if path == "/api/operator/backup" and self.command == "POST":
            u, err = _need_op()
            if err:
                return err
            name = backup_db()
            if not name:
                return self.json(500, {"error": "Zaxira yaratilmadi"})
            audit(u.get("login") or "", u.get("role") or "CEO", "zaxira", name, "qo'lda yaratildi")
            return self.json(200, {"ok": True, "name": name})

        if path == "/api/operator/hall-password" and self.command == "PUT":
            u, err = _need_op()
            if err:
                return err
            d, err = _read_json()
            if err:
                return err
            try:
                hid = int(d.get("id") or 0)
            except Exception:
                return self.json(400, {"error": "id noto'g'ri"})
            new = str(d.get("password") or "").strip()
            if len(new) < 6:
                return self.json(400, {"error": "Parol kamida 6 belgidan iborat bo'lsin"})
            db = get_db()
            h = db.execute("SELECT * FROM halls WHERE id=?", (hid,)).fetchone()
            if not h:
                db.close()
                return self.json(404, {"error": "zal topilmadi"})
            db.execute("UPDATE halls SET pass=? WHERE id=?", (new, hid))
            db.commit()
            db.close()
            audit(u.get("login") or "", u.get("role") or "CEO", "zal_parol", "halls#" + str(hid), h["name"] or "")
            return self.json(200, {"ok": True})

        if path == "/api/operator/super-password" and self.command == "PUT":
            u, err = _need_op()
            if err:
                return err
            d, err = _read_json()
            if err:
                return err
            old = str(d.get("old") or "")
            new = str(d.get("new") or "").strip()
            if len(new) < 6:
                return self.json(400, {"error": "Parol kamida 6 belgidan iborat bo'lsin"})
            s = self.super_settings()
            if old != (s["pass"] or ""):
                audit(u.get("login") or "", u.get("role") or "CEO", "super_parol_xato", "operator", "")
                return self.json(400, {"error": "Eski parol noto'g'ri"})
            set_setting("super_pass", new)
            audit(u.get("login") or "", u.get("role") or "CEO", "super_parol", "operator", "o'zgartirildi")
            return self.json(200, {"ok": True})

        return self.json(404, {"error": "API topilmadi"})

    # ---------- Statik fayllar ----------
    def static(self, path):
        if path in ("", "/"):
            rel = "index.html"
        else:
            rel = path.lstrip("/")
        full = os.path.realpath(os.path.join(ROOT, rel))
        if not full.startswith(os.path.realpath(ROOT) + os.sep) and full != os.path.realpath(ROOT):
            return self.send_error(403)
        if not os.path.isfile(full):
            return self.send_error(404)
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
            ctype += "; charset=utf-8"
        try:
            with open(full, "rb") as f:
                body = f.read()
        except OSError:
            return self.send_error(403)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    # ---------- Asosiy ----------
    def do_GET(self):
        p = urlparse(self.path).path
        try:
            maybe_contract_cleanup()
        except Exception:
            pass
        try:
            track_visit(p, self.headers.get("User-Agent") or "")
        except Exception:
            pass  # statistika xatosi sahifa ochilishini buzmasligi kerak
        if p.startswith("/api/"):
            return self.api(p)
        return self.static(p)

    def do_POST(self):
        p = urlparse(self.path).path
        try:
            maybe_contract_cleanup()
        except Exception:
            pass
        if p.startswith("/api/"):
            return self.api(p)
        return self.json(404, {"error": "API topilmadi"})

    def do_PUT(self):
        p = urlparse(self.path).path
        if p.startswith("/api/"):
            return self.api(p)
        return self.json(404, {"error": "API topilmadi"})

    def do_DELETE(self):
        p = urlparse(self.path).path
        if p.startswith("/api/"):
            return self.api(p)
        return self.json(404, {"error": "API topilmadi"})

    def json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        sys.stderr.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), fmt % args))


class DualStackServer(ThreadingHTTPServer):
    address_family = socket.AF_INET6

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        except OSError:
            pass


_last_contract_cleanup = [0.0]

def maybe_contract_cleanup():
    """Har soatda bir marta muddati o'tgan shartnomalarni tozalaydi (do_GET/do_POST orqali)."""
    import time as _t
    now = _t.time()
    if now - _last_contract_cleanup[0] < 3600:
        return
    _last_contract_cleanup[0] = now
    try:
        cleanup_expired_contracts()
    except Exception:
        pass


def main():
    init_db()
    chat_cleanup()
    try:
        cleanup_expired_contracts()
    except Exception:
        pass
    bname = backup_db()  # xavfsizlik: har ishga tushirishda avto-zaxira
    if bname:
        print("Zaxira yaratildi: backups/%s" % bname)
    srv = DualStackServer((HOST, PORT), Handler)
    print("ELGAKU server ishga tushdi: http://localhost:%d  (ROOT: %s)" % (PORT, ROOT))
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("To'xtatildi.")


if __name__ == "__main__":
    main()
