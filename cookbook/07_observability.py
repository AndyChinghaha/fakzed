"""Cookbook 07: observability & ops — events, traces, metrics, evals,
background runs, scheduler.

Run:  python cookbook/07_observability.py
"""

import time

from _cookbook_utils import scripted

from fakzed import (
    Agent,
    BackgroundRunner,
    EvalCase,
    EventBus,
    MetricsCollector,
    RunObserver,
    Scheduler,
    eval_agent,
)

# ---- 1. RunObserver: one-stop events + metrics ------------------------------
bus = EventBus()
collector = MetricsCollector()
observer = RunObserver(event_bus=bus, metrics=collector)

agent = Agent(
    name="watched",
    model=scripted("你好，已记录本次运行。", "再次问候。"),
    instructions="你是被观测的助手。",
    observer=observer,
)

agent.run("你好")
agent.run("再来一次")

print("1) 事件:", [(e.event_type, e.agent_id) for e in bus.history[-3:]])
summary = collector.summary()
print(
    f"   指标: runs={summary.runs} tokens={summary.total_input_tokens}+{summary.total_output_tokens} tools={summary.total_tool_calls}"
)

# ---- 2. evals ----------------------------------------------------------------
cases = [
    EvalCase(name="greet", input="你好", expected="你好"),
    EvalCase(name="math", input="1+1", expected="2"),
]
report = eval_agent(
    Agent(name="eval-bot", model=scripted("你好，很高兴见到你。", "2")),
    cases,
)
print("2) Evals:", f"accuracy={report.accuracy}")

# ---- 3. background runner ----------------------------------------------------
runner = BackgroundRunner()
run_id = runner.submit(lambda: time.sleep(0.1) or "长任务完成")
result = runner.wait(run_id, timeout=5)
print("3) 后台运行:", result.status, result.result)

# ---- 4. scheduler ------------------------------------------------------------
ticks: list[str] = []
scheduler = Scheduler()
job_id = scheduler.add_job(lambda: ticks.append("tick"), interval_seconds=0.05)
scheduler.start()
time.sleep(0.35)
scheduler.remove_job(job_id)
print("4) 调度器 tick 次数:", len(ticks), "(期望 ≥3)")
