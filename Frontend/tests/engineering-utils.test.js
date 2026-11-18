import test from "node:test";
import assert from "node:assert/strict";
import {
  filterEngineeringTasks,
  getTaskCounts,
  isDependencyCandidate,
  normalizeApiList,
  taskStateLabel,
} from "../src/features/engineering/engineeringUtils.js";

const tasks = [
  { id: 1, project: 10, status: "todo" },
  { id: 2, project: 10, status: "in_progress" },
  { id: 3, project: 10, status: "blocked" },
  { id: 4, project: 20, status: "done" },
];

test("normalizeApiList supports arrays and paginated API responses", () => {
  assert.deepEqual(normalizeApiList(tasks), tasks);
  assert.deepEqual(normalizeApiList({ results: tasks }), tasks);
  assert.deepEqual(normalizeApiList({ results: "invalid" }), []);
  assert.deepEqual(normalizeApiList(null), []);
});

test("filterEngineeringTasks applies project and status filters independently", () => {
  assert.deepEqual(filterEngineeringTasks(tasks).map((task) => task.id), [1, 2, 3, 4]);
  assert.deepEqual(filterEngineeringTasks(tasks, "10").map((task) => task.id), [1, 2, 3]);
  assert.deepEqual(filterEngineeringTasks(tasks, "all", "blocked").map((task) => task.id), [3]);
  assert.deepEqual(filterEngineeringTasks(tasks, "20", "done").map((task) => task.id), [4]);
  assert.deepEqual(filterEngineeringTasks(tasks, "20", "todo"), []);
});

test("getTaskCounts derives totals only from persisted task records", () => {
  assert.deepEqual(getTaskCounts(tasks), {
    total: 4,
    active: 1,
    blocked: 1,
    completed: 1,
  });
  assert.deepEqual(getTaskCounts([]), {
    total: 0,
    active: 0,
    blocked: 0,
    completed: 0,
  });
});

test("isDependencyCandidate rejects self, cross-project and duplicate dependencies", () => {
  const task = { id: 1, project: 10 };
  assert.equal(isDependencyCandidate(task, { id: 2, project: 10 }, []), true);
  assert.equal(isDependencyCandidate(task, { id: 1, project: 10 }, []), false);
  assert.equal(isDependencyCandidate(task, { id: 4, project: 20 }, []), false);
  assert.equal(isDependencyCandidate(task, { id: 2, project: 10 }, [{ depends_on: 2 }]), false);
  assert.equal(isDependencyCandidate(null, { id: 2, project: 10 }, []), false);
});

test("taskStateLabel maps known states and preserves unknown backend states", () => {
  assert.equal(taskStateLabel("in_progress"), "In progress");
  assert.equal(taskStateLabel("done"), "Completed");
  assert.equal(taskStateLabel("custom_state"), "custom_state");
  assert.equal(taskStateLabel(""), "Unknown");
});
