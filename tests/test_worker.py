"""The worker's startup backfill: past complaints reach the case store once, rules only, and stored cases are kept."""
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from agent import llm, tools
from app import store, worker


class Backfill(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        for target, name, value in ((store, "DB_PATH", tmp / "cases.db"),       # never runtime/cases.db
                                    (llm, "PROVIDER", "anthropic")):           # "on", but the backfill turns it off
            patcher = mock.patch.object(target, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        everything = tools.get_db().complaints
        self.some = {cid: everything[cid] for cid in ("CMP-00001", "CMP-00002", "CMP-00467")}
        patcher = mock.patch.object(tools.get_db(), "complaints", dict(self.some))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_processes_only_what_is_missing_and_never_calls_the_llm(self):
        with mock.patch.object(llm, "_call", side_effect=AssertionError("backfill called the LLM")):
            worker.backfill()
        self.assertEqual(store.case_ids(), set(self.some))
        self.assertEqual(store.get_case("CMP-00467")["customer_id"], "CUS-00001")

        before = store.get_case("CMP-00001")
        worker.backfill()                                    # a restart: nothing new, nothing reprocessed
        self.assertEqual(store.get_case("CMP-00001")["updated_at"], before["updated_at"])
        self.assertEqual(len(store.get_case("CMP-00001")["audit"]), len(before["audit"]))

    def test_llm_off_is_per_thread(self):
        seen = {}
        with llm.off():
            seen["here"] = llm.enabled()
            other = threading.Thread(target=lambda: seen.update(there=llm.enabled()))
            other.start()
            other.join()
        self.assertEqual((seen["here"], seen["there"], llm.enabled()), (False, True, True))


if __name__ == "__main__":
    unittest.main()
