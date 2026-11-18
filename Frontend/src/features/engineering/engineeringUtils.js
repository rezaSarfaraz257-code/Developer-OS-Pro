export const TASK_STATES = [
  ["todo", "Planned"],
  ["in_progress", "In progress"],
  ["blocked", "Blocked"],
  ["done", "Completed"],
];


/** Validate a strict YYYY-MM-DD calendar date without timezone parsing. */
export function isValidDateOnly(value) {
  if (typeof value !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [year, month, day] = value.split("-").map(Number);
  if (year < 1) return false;
  const parsed = new Date(0);
  parsed.setUTCHours(0, 0, 0, 0);
  parsed.setUTCFullYear(year, month - 1, day);
  return parsed.getUTCFullYear() === year &&
    parsed.getUTCMonth() === month - 1 &&
    parsed.getUTCDate() === day;
}

export function normalizeApiList(value) {
  const records = Array.isArray(value)
    ? value
    : Array.isArray(value?.results)
      ? value.results
      : [];
  // Ignore malformed collection entries before they reach UI renderers or
  // derived metrics; valid backend records are plain JSON objects.
  return records.filter((record) => record !== null && typeof record === "object" && !Array.isArray(record));
}

export function filterEngineeringTasks(tasks, projectId = "all", statusFilter = "all") {
  return normalizeApiList(tasks).filter((task) => {
    const matchesProject = projectId === "all" || String(task.project) === String(projectId);
    const matchesStatus = statusFilter === "all" || task.status === statusFilter;
    return matchesProject && matchesStatus;
  });
}

export function getTaskCounts(tasks) {
  const records = normalizeApiList(tasks);
  return {
    total: records.length,
    active: records.filter((task) => task.status === "in_progress").length,
    blocked: records.filter((task) => task.status === "blocked").length,
    completed: records.filter((task) => task.status === "done").length,
  };
}

export function taskStateLabel(status) {
  return TASK_STATES.find(([value]) => value === status)?.[1] || status || "Unknown";
}

export function isDependencyCandidate(task, candidate, dependencies = []) {
  if (!task || !candidate || task.id == null || candidate.id == null) return false;
  if (task.project == null || candidate.project == null) return false;
  if (String(task.id) === String(candidate.id)) return false;
  if (String(task.project) !== String(candidate.project)) return false;
  return !normalizeApiList(dependencies).some(
    (dependency) => dependency.depends_on != null &&
      String(dependency.depends_on) === String(candidate.id),
  );
}

/**
 * Parse date-only API values as local calendar dates. Native Date parsing
 * treats YYYY-MM-DD as UTC, which can display the previous day west of UTC.
 * Timestamp values retain their normal instant-based parsing semantics.
 */
export function parseEngineeringDate(value) {
  if (value instanceof Date) {
    return Number.isFinite(value.getTime()) ? new Date(value.getTime()) : null;
  }
  if (typeof value !== "string" || !value) return null;
  if (/^\\d{4}-\\d{2}-\\d{2}$/.test(value)) {
    if (!isValidDateOnly(value)) return null;
    const [year, month, day] = value.split("-").map(Number);
    return new Date(year, month - 1, day);
  }
  const parsed = new Date(value);
  return Number.isFinite(parsed.getTime()) ? parsed : null;
}


/**
 * Parse a successful API response without assuming every proxy/server response
 * is valid JSON. API endpoints in this feature have JSON contracts.
 */
export async function parseApiResponse(response) {
  if (response.status === 204) return null;
  const body = await response.text();
  if (!body.trim()) return null;
  try {
    return JSON.parse(body);
  } catch {
    const status = response.status ? ` (HTTP ${response.status})` : "";
    throw new Error(`The API returned an invalid response${status}. Check the server or proxy logs.`);
  }
}


/**
 * Derive operational signals from persisted API records.
 * These are descriptive counts only; they never imply agent execution or
 * independently verified project health.
 */
export function getEngineeringInsights(tasks, projects, workspaces, now = new Date()) {
  const taskRecords = normalizeApiList(tasks);
  const projectRecords = normalizeApiList(projects);
  const workspaceRecords = normalizeApiList(workspaces);
  const today = now instanceof Date && Number.isFinite(now.getTime())
    ? [
      now.getFullYear(),
      String(now.getMonth() + 1).padStart(2, "0"),
      String(now.getDate()).padStart(2, "0"),
    ].join("-")
    : null;

  const openTasks = taskRecords.filter((task) => task.status !== "done");
  const overdue = today
    ? openTasks.filter((task) => isValidDateOnly(task.due_date) && task.due_date < today).length
    : 0;
  const unassigned = openTasks.filter((task) => task.assignee == null || task.assignee === "").length;

  return {
    overdue,
    unassigned,
    activeProjects: projectRecords.filter((project) =>
      project.status === "In Progress" || project.status === "Planning"
    ).length,
    configuredWorkspaces: workspaceRecords.filter((workspace) => workspace?.id != null).length,
  };
}
