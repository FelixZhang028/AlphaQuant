"""管理后台的数据工具：财报季自动更新财务数据、每日更新的每一步结果、手动备份和服务器状态。"""
import sqlite3
from collections import namedtuple
from datetime import date, datetime, timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import database
from app.quant import backup, daily_schedule, fundamentals_schedule as fs
from app.routes import admin, auth

CHINA = daily_schedule.CHINA


def at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=CHINA)


def run(day: date, status: str, hour: int = 10, trigger: str = "auto", datasets=None) -> dict:
    stamp = at(day, hour).isoformat()
    return {"datasets": datasets or ["fundamentals"], "trigger": trigger, "status": status, "created_at": stamp, "updated_at": stamp}


def test_financial_data_updates_on_saturdays_of_report_seasons():
    assert fs.runs_day(date(2026, 4, 18))                      # 4 月的周六
    assert not fs.runs_day(date(2026, 4, 17))                  # 周五
    assert not fs.runs_day(date(2026, 6, 13))                  # 6 月没有新财报
    assert fs.runs_day(date(2026, 5, 2)) and not fs.runs_day(date(2026, 5, 9))   # 5 月只有第一个周六
    assert fs.next_run(date(2026, 6, 1)) == date(2026, 7, 4)
    assert fs.window(date(2026, 4, 18)) == (date(2026, 4, 18) - timedelta(days=450), date(2026, 4, 18))


def test_the_schedule_starts_once_and_retries_failures_later():
    saturday = date(2026, 10, 17)
    assert fs.decide([], at(saturday, 9)).state == "waiting"                           # 10 点以前
    assert fs.decide([], at(saturday, 10, 5)).start
    assert not fs.decide([], at(saturday - timedelta(days=1), 12)).start             # 周五
    assert fs.decide([run(saturday, "RUNNING")], at(saturday, 11)).state == "running"
    assert fs.decide([run(saturday, "SUCCESS")], at(saturday, 12)).state == "done"
    assert fs.decide([run(saturday, "STOPPED")], at(saturday, 12)).state == "done"
    failed = [run(saturday, "FAILED", hour=10)]
    assert not fs.decide(failed, at(saturday, 10, 30)).start                          # 1 小时后再试
    assert fs.decide(failed, at(saturday, 11, 30)).start
    three = [run(saturday, "FAILED", hour=h) for h in (14, 12, 10)]
    assert fs.decide(three, at(saturday, 16)).state == "failed"
    other = [run(saturday, "RUNNING", trigger="admin", datasets=["bars"])]
    assert fs.decide(other, at(saturday, 11)).text == "等别的数据任务完成后再更新"
    assert fs.decide([run(saturday, "SUCCESS", trigger="admin")], at(saturday, 12)).start   # 手动的不算自动的那一次
    assert fs.decide([], at(saturday, 12), on=False).state == "disabled"


def test_the_scheduler_starts_a_financial_data_job_for_recent_quarters():
    class Jobs:
        def __init__(self):
            self.started = []

        def records(self):
            return []

        def start(self, start, end, datasets, trigger="admin"):
            self.started.append((start, end, datasets, trigger))

    jobs = Jobs()
    saturday = date(2026, 10, 17)
    assert fs.FundamentalsScheduler(jobs).tick(at(saturday, 10, 30))
    assert jobs.started == [(saturday - timedelta(days=450), saturday, ["fundamentals"], "auto")]
    assert not fs.FundamentalsScheduler(jobs).tick(at(saturday + timedelta(days=2), 10, 30))   # 周一不更新


def test_status_shows_the_last_automatic_run():
    saturday = date(2026, 10, 17)
    done = {**run(saturday, "SUCCESS"), "start_date": "2025-07-24", "end_date": "2026-10-17",
            "result": {"quarterly_fundamentals": {"reports": 12}}}
    info = fs.status([done], at(saturday, 15))
    assert info["state"] == "done" and info["last"]["result"]["quarterly_fundamentals"]["reports"] == 12
    assert info["next_run"] == "2026-10-17"


def test_each_daily_step_says_done_failed_or_not_run():
    result = {"steps": {"security_master": {"rows": 5600}, "daily_bars": {"symbols": 5200, "new_listings": 3}},
              "errors": {"industry": "网络超时"}}
    steps = {item["key"]: item for item in daily_schedule.step_results(result)}
    assert steps["security_master"] == {"key": "security_master", "label": "股票列表", "state": "done", "text": "5,600 只证券"}
    assert steps["daily_bars"]["text"] == "5,200 只股票，其中新上市 3 只"
    assert steps["industry"]["state"] == "failed" and steps["industry"]["text"] == "网络超时"
    assert steps["derived"]["state"] == "skipped"
    assert list(steps) == list(daily_schedule.STEP_NAMES)


def make_db(path):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE users (id INTEGER)")
    conn.commit()
    conn.close()


def test_manual_backups_are_kept_apart_from_daily_ones(tmp_path, monkeypatch):
    db, runtime, root = tmp_path / "app.db", tmp_path / "runtime", tmp_path / "backups"
    make_db(db)
    runtime.mkdir()
    monkeypatch.setenv("FELLOWQUANT_BACKUP_KEEP", "2")
    monkeypatch.setattr(backup, "MANUAL_KEEP", 2)
    for day in (16, 17, 18):
        backup.backup(date(2026, 10, day), root=root, database=db, runtime=runtime)
    stamps = iter(["101000", "102000", "103000"])

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.strptime(next(stamps), "%H%M%S")

    monkeypatch.setattr(backup, "datetime", Clock)
    for _ in range(3):
        assert backup.backup(date(2026, 10, 18), root=root, database=db, runtime=runtime, manual=True) is not None
    names = [item["name"] for item in backup.listing(root)]
    assert names == ["2026-10-18-manual-103000", "2026-10-18-manual-102000", "2026-10-18", "2026-10-17"]
    assert all(item["size"] > 0 for item in backup.listing(root))
    assert backup.listing(tmp_path / "missing") == []


def test_admin_system_status_and_manual_backup(tmp_path, monkeypatch):
    import app.routes.workspace as workspace

    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "app.db"))
    database.init_db()
    monkeypatch.setenv("FELLOWQUANT_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setattr(admin, "MARKET_ROOT", tmp_path / "market")
    monkeypatch.setattr(admin, "RUNTIME_ROOT", tmp_path / "runtime")
    monkeypatch.setattr(backup, "RUNTIME_ROOT", tmp_path / "runtime")
    monkeypatch.setattr(backup, "DB_PATH", str(tmp_path / "app.db"))
    (tmp_path / "market").mkdir()
    (tmp_path / "market" / "bars.parquet").write_bytes(b"x" * 2048)
    (tmp_path / "runtime").mkdir()
    admin._size_cache.clear()
    usage = namedtuple("Usage", "total used free")
    monkeypatch.setattr(admin.shutil, "disk_usage", lambda path: usage(100 * 1024 ** 3, 97 * 1024 ** 3, 3 * 1024 ** 3))

    class Jobs:
        def records(self):
            return []

    monkeypatch.setattr(workspace, "_data_jobs", lambda: Jobs())
    app = FastAPI()
    app.include_router(auth.router)
    app.include_router(admin.router)
    client = TestClient(app)
    client.post("/api/v1/auth/register", json={"name": "管理员", "email": "boss@example.test", "password": "correct horse 1"})
    with database.get_conn() as conn:
        conn.execute("UPDATE users SET is_admin = 1")
    login = client.post("/api/v1/auth/login", json={"email": "boss@example.test", "password": "correct horse 1"})
    token = {"Authorization": "Bearer " + login.json()["token"]}
    info = client.get("/api/v1/admin/system", headers=token).json()
    assert info["disk"]["warning"] is True and info["disk"]["free"] == 3 * 1024 ** 3     # 少于 5 GB 就提醒
    assert info["sizes"]["market"] == 2048 and info["backups"]["items"] == []
    assert info["fundamentals"]["enabled"] is True and "next_run" in info["fundamentals"]
    made = client.post("/api/v1/admin/backup", headers=token)
    assert made.status_code == 201 and "-manual-" in made.json()["name"]
    assert [item["manual"] for item in client.get("/api/v1/admin/system", headers=token).json()["backups"]["items"]] == [True]
