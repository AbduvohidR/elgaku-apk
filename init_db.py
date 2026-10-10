# -*- coding: utf-8 -*-
import sqlite3, os
p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "elgaku.db")
db = sqlite3.connect(p)
c = db.cursor()
c.executescript("""
CREATE TABLE IF NOT EXISTS partners(
  id INTEGER PRIMARY KEY, hall TEXT, type TEXT, status TEXT,
  city TEXT, address TEXT, commission REAL, source TEXT, created TEXT,
  duplicate INTEGER DEFAULT 0, complaints INTEGER DEFAULT 0, testMode INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS complaints(
  id INTEGER PRIMARY KEY, partner_id INTEGER, reason TEXT,
  count INTEGER, status TEXT, date TEXT
);
CREATE TABLE IF NOT EXISTS payouts(
  id INTEGER PRIMARY KEY, partner_id INTEGER, period TEXT,
  revenue INTEGER, payout INTEGER, status TEXT
);
CREATE TABLE IF NOT EXISTS halls(
  id INTEGER PRIMARY KEY, name TEXT, owner TEXT, status TEXT
);
""")
db.commit()
tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print("DB:", p, os.path.getsize(p), "bytes")
print("Tables:", tables)
db.close()
