from investigation_world.tasks.spec import generate_tasks,split_manifest,TaskFamily
def test_task_families_and_splits():
 tasks=generate_tasks('WORLD-1',48,7); assert {t.family for t in tasks}==set(TaskFamily); assert any(not t.answerable for t in tasks)
 m=split_manifest(); assert not (set(m['train'])&set(m['private_eval']))
