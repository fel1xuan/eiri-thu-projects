import json
import os
from pathlib import Path
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from utils.runtime_paths import ORGANIZATION_NAME, prepare_runtime_environment
from utils.version import APP_DISPLAY_VERSION, APP_NAME, APP_VERSION


def main():
    prepare_runtime_environment()
    from ui.main_window import MainWindow

    QApplication.setOrganizationName(ORGANIZATION_NAME)
    QApplication.setApplicationName(APP_NAME)
    QApplication.setApplicationVersion(APP_VERSION)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)

    window = MainWindow()
    window.show()
    _schedule_smoke_test_if_requested(app, window)

    sys.exit(app.exec())


def _schedule_smoke_test_if_requested(app, window):
    report_path = os.environ.get("QH_APP_SMOKE_TEST_REPORT", "")
    if not report_path:
        return

    def run_smoke_test():
        result = {"success": False}
        try:
            from utils.config_utils import get_config_path, load_config, save_config
            from utils.log_utils import append_run_log, get_run_log_path, read_run_logs
            from utils.resource_utils import resource_exists, resource_path

            page_labels = [label for label, _ in window.pages]
            for index in range(window.stack.count()):
                window._set_current_page(index)
                QApplication.processEvents()

            config = load_config()
            save_config(config)
            log_path = append_run_log("Mac打包测试", "success", "App冒烟测试启动、页面切换、配置读写和日志追加通过")
            logs = read_run_logs()

            result = {
                "success": True,
                "window_title": window.windowTitle(),
                "app_version": APP_VERSION,
                "display_version": APP_DISPLAY_VERSION,
                "page_count": window.stack.count(),
                "page_labels": page_labels,
                "config_path": get_config_path(),
                "step3_result_dir": config.get("step3_result_dir", ""),
                "run_log_path": get_run_log_path(),
                "run_log_append_path": log_path,
                "run_log_count": len(logs),
                "logo_path": resource_path("assets/logo.png"),
                "logo_exists": resource_exists("assets/logo.png"),
                "default_config_exists": resource_exists("config/default_config.json"),
                "version_config_exists": resource_exists("config/version.json"),
                "physical_data_path_exists": resource_exists("assets/mindmaps/physical_data_path.png"),
                "code_data_analysis_flow_exists": resource_exists("assets/mindmaps/code_data_analysis_flow.png"),
            }
            chart_source = os.environ.get("QH_APP_SMOKE_TEST_15MIN_DIR", "").strip()
            if chart_source:
                chart_page = next(page for label, page in window.pages if label == "结果查看")
                chart_page.tabs.setCurrentIndex(1)
                chart_page.chart_path_input.setText(chart_source)
                chart_page.load_chart_data()
                if not chart_page.chart_data:
                    raise RuntimeError(chart_page.chart_status_label.text())
                chart_page.select_all_current_category()
                chart_page.plot_chart()
                chart_image = os.environ.get("QH_APP_SMOKE_TEST_CHART_IMAGE", "").strip()
                if chart_image:
                    chart_page.figure.savefig(chart_image, dpi=120)
                chart_result = chart_page.chart_data
                result["chart"] = {
                    "files": len(chart_result.get("files", [])),
                    "files_read": chart_result.get("files_read", 0),
                    "rows": chart_result.get("rows", 0),
                    "time_start": str(chart_result.get("time_start")),
                    "time_end": str(chart_result.get("time_end")),
                    "missing_dates": chart_result.get("missing_dates", []),
                    "duplicate_count": chart_result.get("duplicate_count", 0),
                    "numeric_columns": len(chart_result.get("numeric_columns", [])),
                    "categories": {
                        category: len(fields)
                        for category, fields in chart_result.get("field_categories", {}).items()
                    },
                    "selected_category": chart_page.current_category,
                    "selected_fields": chart_page._checked_fields(),
                    "plot_lines": len(chart_page.figure.axes[0].lines) if chart_page.figure.axes else 0,
                    "image_path": chart_image,
                    "image_exists": bool(chart_image and Path(chart_image).is_file()),
                }
        except Exception as exc:
            result = {"success": False, "error": str(exc)}
        finally:
            path = Path(report_path).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            app.quit()

    QTimer.singleShot(300, run_smoke_test)


if __name__ == "__main__":
    main()
