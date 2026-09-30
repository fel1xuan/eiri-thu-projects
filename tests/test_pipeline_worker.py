import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QThread, QTimer
from PySide6.QtWidgets import QApplication

from ui.pipeline_worker import PipelineProgressTracker, PipelineWorker


class PipelineWorkerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_three_day_progress_weights_and_daily_counts(self):
        tracker = PipelineProgressTracker(3)

        self.assertEqual(self._progress(tracker.consume("[成功] 1号低频汇总：完成")), 10)

        step2_progress = []
        for date_text in ("2026-04-01", "2026-04-02", "2026-04-03"):
            events = tracker.consume(f"[2号] 秒级结果保存：/tmp/{date_text}_秒级CO2排放结果.xlsx")
            step2_progress.append(self._progress(events))
        self.assertEqual(step2_progress, [33, 57, 80])

        step3_progress = []
        for date_text in ("2026-04-01", "2026-04-02", "2026-04-03"):
            events = tracker.consume(f"[3号] 处理完成：/tmp/{date_text}_15minCO2排放结果.xlsx，共生成96行")
            step3_progress.append(self._progress(events))
        self.assertEqual(step3_progress, [87, 93, 100])

    def test_worker_keeps_event_loop_responsive_and_filters_ui_log(self):
        config = {
            "target_month": "2026-04",
            "process_start_date": "2026-04-01",
            "process_end_date": "2026-04-03",
        }

        def fake_runner(_config, logger=None):
            logger("[进行中] 1号低频汇总")
            time.sleep(0.02)
            logger("[1号] 正在读取历史低频主表")
            logger("[成功] 1号低频汇总：完成")
            logger("[进行中] 2号秒级核算")
            for date_text in ("2026-04-01", "2026-04-02", "2026-04-03"):
                logger(f"[2号] 正在处理日期：{date_text}")
                logger("[2号] 正在合并CEMS数据...")
                time.sleep(0.02)
                logger(f"[2号] 秒级结果保存：/tmp/{date_text}_秒级CO2排放结果.xlsx")
            logger("[成功] 2号秒级核算：完成")
            logger("[进行中] 3号15min聚合")
            for date_text in ("2026-04-01", "2026-04-02", "2026-04-03"):
                logger(f"[3号] 正在处理：{date_text}")
                time.sleep(0.01)
                logger(f"[3号] 处理完成：/tmp/{date_text}_15minCO2排放结果.xlsx，共生成96行")
            logger("[成功] 3号15min聚合：完成")
            return {"success": True, "message": "完成", "steps": [], "output_files": [], "config_updates": {}}

        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            os.environ, {"QH_DATA_ANALYSIS_DATA_DIR": temp_dir}
        ):
            worker = PipelineWorker(config, runner=fake_runner)
            thread = QThread()
            worker.moveToThread(thread)
            summaries = []
            progresses = []
            detail_paths = []
            result_holder = []
            heartbeat = {"count": 0}
            timer = QTimer()
            timer.setInterval(5)
            timer.timeout.connect(lambda: heartbeat.__setitem__("count", heartbeat["count"] + 1))
            loop = QEventLoop()

            worker.summary_log.connect(summaries.append)
            worker.progress_changed.connect(progresses.append)
            worker.detail_log_ready.connect(detail_paths.append)
            worker.finished.connect(result_holder.append)
            worker.finished.connect(thread.quit)
            thread.started.connect(worker.run)
            thread.finished.connect(loop.quit)
            timer.start()
            thread.start()
            QTimer.singleShot(5000, loop.quit)
            loop.exec()
            timer.stop()
            thread.wait(1000)

            self.assertFalse(thread.isRunning())
            self.assertGreater(heartbeat["count"], 5)
            self.assertTrue(result_holder[0]["success"])
            self.assertEqual(progresses[-1], 100)
            self.assertTrue(any("2026-04-03 完成" in line for line in summaries))
            self.assertFalse(any("合并CEMS" in line for line in summaries))
            detail_text = Path(detail_paths[0]).read_text(encoding="utf-8")
            self.assertIn("正在合并CEMS数据", detail_text)

    @staticmethod
    def _progress(events):
        values = [event["value"] for event in events if event["type"] == "progress"]
        return values[-1] if values else None


if __name__ == "__main__":
    unittest.main()
