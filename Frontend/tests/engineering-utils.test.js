import test from "node:test";
import assert from "node:assert/strict";
import {
  filterEngineeringTasks,
  getTaskCounts,
  getEngineeringInsights,
  isDependencyCandidate,
  normalizeApiList,
  taskStateLabel,
  isValidDateOnly,
  parseEngineeringDate,
  reconcileRecordSelection,
  reconcileProjectSelection,
} from "../src/features/engineering/engineeringUtils.js";

const tasks = [
  { id: 1, project: 10, status: "todo" },
  { id: 2, project: 10, status: "in_progress" },
  { id: 3, project: 10, status: "blocked" },
  { id: 4, project: 20, status: "done" },
];

test("isValidDateOnly accepts real calendar dates and rejects malformed values", () => {
  assert.equal(isValidDateOnly("2024-02-29"), true);
  assert.equal(isValidDateOnly("2000-02-29"), true);
  assert.equal(isValidDateOnly("1900-02-29"), false);
  assert.equal(isValidDateOnly("2026-02-30"), false);
  assert.equal(isValidDateOnly("2026-13-01"), false);
  assert.equal(isValidDateOnly("2026-01-00"), false);
  assert.equal(isValidDateOnly("0000-01-01"), false);
  assert.equal(isValidDateOnly("2026-11-18T00:00:00Z"), false);
  assert.equal(isValidDateOnly(null), false);
});

test("parseEngineeringDate preserves date-only calendar days and validates values", () => {
  const dateOnly = parseEngineeringDate("2026-11-19");
  assert.ok(dateOnly instanceof Date);
  assert.equal(dateOnly.getFullYear(), 2026);
  assert.equal(dateOnly.getMonth(), 10);
  assert.equal(dateOnly.getDate(), 19);
  const earlyYear = parseEngineeringDate("0001-01-02");
  assert.equal(earlyYear.getFullYear(), 1);
  assert.equal(earlyYear.getMonth(), 0);
  assert.equal(earlyYear.getDate(), 2);
  assert.equal(parseEngineeringDate("2026-02-30"), null);
  assert.equal(parseEngineeringDate("not-a-date"), null);
  assert.equal(parseEngineeringDate(null), null);
  const timestamp = parseEngineeringDate("2026-11-19T12:30:00Z");
  assert.ok(timestamp instanceof Date);
  assert.equal(timestamp.toISOString(), "2026-11-19T12:30:00.000Z");
});

test("normalizeApiList supports arrays and paginated API responses", () => {
  assert.deepEqual(normalizeApiList(tasks), tasks);
  assert.deepEqual(normalizeApiList({ results: tasks }), tasks);
  assert.deepEqual(normalizeApiList({ results: "invalid" }), []);
  assert.deepEqual(normalizeApiList([tasks[0], null, "invalid", [], tasks[1]]), [tasks[0], tasks[1]]);
  assert.deepEqual(normalizeApiList({ results: [null, tasks[2], 42] }), [tasks[2]]);
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
  assert.equal(isDependencyCandidate({ id: null, project: 10 }, { id: 2, project: 10 }, []), false);
  assert.equal(isDependencyCandidate({ id: 1 }, { id: 2 }, []), false);
  assert.equal(isDependencyCandidate(task, { id: 2, project: 10 }, [null]), true);
});

test("taskStateLabel maps known states and preserves unknown backend states", () => {
  assert.equal(taskStateLabel("in_progress"), "In progress");
  assert.equal(taskStateLabel("done"), "Completed");
  assert.equal(taskStateLabel("custom_state"), "custom_state");
  assert.equal(taskStateLabel(""), "Unknown");
});


test("parseApiResponse handles empty, no-content and valid JSON responses", async () => {
  const { parseApiResponse } = await import("../src/features/engineering/engineeringUtils.js");
  assert.equal(await parseApiResponse(new Response(null, { status: 204 })), null);
  assert.equal(await parseApiResponse(new Response("  ", { status: 200 })), null);
  assert.deepEqual(await parseApiResponse(new Response(JSON.stringify({ id: 7 }), { status: 200 })), { id: 7 });
});

test("parseApiResponse reports invalid proxy/server responses clearly", async () => {
  const { parseApiResponse } = await import("../src/features/engineering/engineeringUtils.js");
  await assert.rejects(
    parseApiResponse(new Response("<html>Bad Gateway</html>", { status: 502 })),
    /invalid response \(HTTP 502\)/,
  );
});


test("getEngineeringInsights derives overdue, unassigned and capacity counts from API records", () => {
  const now = new Date(2026, 10, 19, 12);
  const records = [
    { id: 1, status: "in_progress", due_date: "2026-11-18", assignee: null },
    { id: 2, status: "todo", due_date: "2026-11-19", assignee: 7 },
    { id: 3, status: "done", due_date: "2026-11-01", assignee: null },
    { id: 4, status: "blocked", due_date: "not-a-date", assignee: "" },
    { id: 5, status: "todo", assignee: 8 },
    { id: 6, status: "todo", due_date: "2026-02-30", assignee: 8 },
    { id: 7, status: "todo", due_date: "2024-02-29", assignee: 8 },
  ];
  const projects = [
    { id: 10, status: "In Progress" },
    { id: 11, status: "Planning" },
    { id: 12, status: "Completed" },
    { id: 13, status: "On Hold" },
  ];
  const workspaces = [{ id: 1 }, { id: 2 }, { name: "missing id" }];

  assert.deepEqual(getEngineeringInsights(records, projects, workspaces, now), {
    overdue: 2,
    unassigned: 2,
    activeProjects: 2,
    configuredWorkspaces: 2,
  });
});

test("getEngineeringInsights returns no overdue signal for an invalid clock value", () => {
  assert.deepEqual(getEngineeringInsights(
    [{ status: "todo", due_date: "2020-01-01", assignee: null }],
    [],
    [],
    new Date("invalid"),
  ), {
    overdue: 0,
    unassigned: 1,
    activeProjects: 0,
    configuredWorkspaces: 0,
  });
});

test("getEngineeringInsights safely handles empty and paginated API payloads", () => {
  assert.deepEqual(getEngineeringInsights(
    { results: [] },
    null,
    { results: [{ id: 1 }] },
    new Date(2026, 10, 19),
  ), {
    overdue: 0,
    unassigned: 0,
    activeProjects: 0,
    configuredWorkspaces: 1,
  });
});


test("reconcileRecordSelection preserves valid selections and clears deleted records", () => {
  const records = [{ id: 1 }, { id: 2 }];
  assert.equal(reconcileRecordSelection(records, 2), "2");
  assert.equal(reconcileRecordSelection(records, "1"), "1");
  assert.equal(reconcileRecordSelection(records, 99), "1");
  assert.equal(reconcileRecordSelection([], 99), "");
  assert.equal(reconcileRecordSelection([{ name: "invalid id" }], 99), "undefined");
});

test("reconcileProjectSelection preserves the all filter and resets deleted projects", () => {
  const projects = [{ id: 10 }, { id: 20 }];
  assert.equal(reconcileProjectSelection(projects, "all"), "all");
  assert.equal(reconcileProjectSelection(projects, 20), "20");
  assert.equal(reconcileProjectSelection(projects, "999"), "all");
  assert.equal(reconcileProjectSelection([], "10"), "all");
});
