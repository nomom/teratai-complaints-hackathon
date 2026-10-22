"""Rules extractor regressions: phrasings the keyword rules used to get wrong. Run: python -m unittest discover tests

The rules are the offline path and the fallback whenever the LLM fails, so they must stay strong on their own.
"""
import unittest

from agent import extract, tools


def rules(text, subject=""):
    return extract.extract_rules({"complaint_id": "T", "customer_id": "CUS-00150", "received_at": "2026-09-30 10:00",
                                  "channel": "App chat", "subject": subject, "text": text})


class Category(unittest.TestCase):
    def setUp(self):
        tools.get_db()

    def test_scams_are_never_failed_transfers(self):        # critical errors when missed
        for text in [
            "Saya melabur RM4,042.06 dalam skim pelaburan dari kumpulan chat dan pindahkan kepada Muthu hari Ahad lepas.",
            "Customer called, distressed. Reports being deceived by an online acquaintance into transferring RM12,754.42.",
            "Assalamualaikum, kenalan dalam talian minta RM 349.52 untuk kecemasan perubatan dan saya pindahkan kepada Ganesan.",
        ]:
            with self.subTest(text=text[:40]):
                self.assertEqual(rules(text).category, "SCAM_TRANSFER")

    def test_atm_without_the_word_atm(self):
        for text in [
            "Saya mengeluarkan RM600 di Klang Station semalam tetapi wang tidak keluar sepenuhnya.",
            "The machine did not dispense all of the cash when I withdrew RM1500.00 today.",
            "I withdrew RM300 last Tuesday but the machine did not give me the cash.",
            "Salam, withdraw RM500.00 kat Klang Mall last Tuesday, duit tak keluar full.",
        ]:
            with self.subTest(text=text[:40]):
                self.assertEqual(rules(text).category, "ATM_NOT_DISPENSED")

    def test_service_complaints_stay_service(self):
        for text in ["Saya telefon talian khidmat pelanggan lima kali semalam tetapi tiada siapa yang menjawab.",
                     "The Kepong branch closed before the posted hours and I could not deposit my cheque."]:
            with self.subTest(text=text[:40]):
                self.assertEqual(rules(text).category, "SERVICE_QUALITY")


class Language(unittest.TestCase):
    def test_detect(self):
        cases = {
            "Mesin deposit tunai di cawangan Ipoh sudah rosak seminggu.": "MS",          # no common words before
            "Mesin ATM di Shah Alam Branch tidak mengeluarkan wang RM 500.00.": "MS",      # "Branch" is a name
            "Saya tidak membuat pembayaran RM150 di BETZONE ONLINE (kad berakhir 0824).": "MS",
            "Pindahan RM 2,727.49 kepada Saravanan a/l Pillai hari ini tidak sampai.": "MS",  # "a/l" is not English
            "app asyik logout sendiri 3 hari dah, tak boleh bayar bil.": "MIXED",
            "Hi, kenapa ada monthly service charge RM10 bulan Julai? Mohon bantu, urgent.": "MIXED",
            "I withdrew RM300 at Kota Bharu Market but the machine did not give me the cash.": "EN",
            "My DuitNow transfer to Siti Nadia binti Hassan failed but the money was deducted.": "EN",
        }
        for text, want in cases.items():
            with self.subTest(text=text[:40]):
                self.assertEqual(extract.detect_language(text), want)


if __name__ == "__main__":
    unittest.main()
