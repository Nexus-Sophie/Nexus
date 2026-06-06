# Celery worker
The worker is for agent execution. Two tasks are avaliable - coding and pm.

# Notice
任务使用 late ack。推荐 warm shutdown，让 worker 有机会完成任务或把未 ack 的消息交还给 broker。cold shutdown 后任务会依赖 Celery/Redis visibility timeout 重投递，并从 PostgreSQL checkpoint 继续。
