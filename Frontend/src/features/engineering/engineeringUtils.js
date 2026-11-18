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
