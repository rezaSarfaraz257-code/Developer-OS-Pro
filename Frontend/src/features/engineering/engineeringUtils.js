export const TASK_STATES = [
  ["todo", "Planned"],
  ["in_progress", "In progress"],
  ["blocked", "Blocked"],
  ["done", "Completed"],
];

export function normalizeApiList(value) {
  if (Array.isArray(value)) return value;
  if (Array.isArray(value?.results)) return value.results;
  return [];
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
  if (!task || !candidate) return false;
  if (String(task.id) === String(candidate.id)) return false;
  if (String(task.project) !== String(candidate.project)) return false;
  return !dependencies.some((dependency) => String(dependency.depends_on) === String(candidate.id));
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
  const today = [
    now.getFullYear(),
    String(now.getMonth() + 1).padStart(2, "0"),
    String(now.getDate()).padStart(2, "0"),
  ].join("-");

  const openTasks = taskRecords.filter((task) => task.status !== "done");
  const overdue = openTasks.filter((task) => {
    const dueDate = typeof task.due_date === "string" ? task.due_date.slice(0, 10) : "";
    if (!/^\d{4}-\d{2}-\d{2}$/.test(dueDate)) return false;
    const [year, month, day] = dueDate.split("-").map(Number);
    // Use UTC calendar arithmetic so daylight-saving transitions and
    // local timezone offsets cannot change date-only deadline validation.
    const parsed = new Date(0);
    parsed.setUTCHours(0, 0, 0, 0);
    parsed.setUTCFullYear(year, month - 1, day);
    const isCalendarDate =
      parsed.getUTCFullYear() === year &&
      parsed.getUTCMonth() === month - 1 &&
      parsed.getUTCDate() === day;
    return isCalendarDate && dueDate < today;
  }).length;
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
