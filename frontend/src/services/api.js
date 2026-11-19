const defaultApiBase = typeof window === "undefined"
  ? "http://127.0.0.1:5000"
  : `${window.location.protocol}//${window.location.host.replace(/:\d+$/, "")}:5000`;

export const API_BASE =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") || defaultApiBase;

let csrfToken = "";
let cachedSessionIdentifier = "";
let authStateRequest = null;

export function createRequestKey() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (character) => {
    const random = Math.floor(Math.random() * 16);
    return (character === "x" ? random : (random & 0x3) | 0x8).toString(16);
  });
}

async function requestJson(path, options = {}, retryCsrf = true) {
  const method = (options.method || "GET").toUpperCase();
  const csrfProtected = ["POST", "PUT", "PATCH", "DELETE"].includes(method);
  if (csrfProtected && !csrfToken) {
    await getAuthState();
  }

  const headers = { ...(options.body ? { "Content-Type": "application/json" } : {}), ...options.headers };
  if (csrfProtected && csrfToken) {
    headers["X-CSRF-Token"] = csrfToken;
  }
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    ...options,
    headers,
  });
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error("The server returned an invalid response");
  }
  if (data.csrf_token) csrfToken = data.csrf_token;
  if (!response.ok) {
    if (
      retryCsrf
      && csrfProtected
      && response.status === 403
      && data.error === "CSRF token is missing or invalid"
    ) {
      csrfToken = "";
      await getAuthState();
      return requestJson(path, options, false);
    }
    const error = new Error(data.error || "API request failed");
    error.status = response.status;
    error.data = data;
    throw error;
  }
  return data;
}

function getAuthState() {
  if (!authStateRequest) {
    authStateRequest = requestJson("/api/auth/me").finally(() => {
      authStateRequest = null;
    });
  }
  return authStateRequest;
}

function postJson(path, payload) {
  return requestJson(path, { method: "POST", body: JSON.stringify(payload) });
}

export async function getCurrentUser() {
  const data = await getAuthState();
  return data.user;
}

export function registerStudent({ username, password, grade }) {
  return postJson("/api/auth/register", {
    username,
    password,
    ...(grade ? { grade: Number(grade) } : {}),
  });
}

export function loginStudent({ username, password }) {
  return postJson("/api/auth/login", { username, password });
}

export async function logoutStudent() {
  await postJson("/api/auth/logout", {});
  csrfToken = "";
  cachedSessionIdentifier = "";
  sessionStorage.removeItem("learning-session-identifier");
}

export async function startLearningSession() {
  let identifier = sessionStorage.getItem("learning-session-identifier");
  if (!identifier) {
    identifier = createRequestKey();
    sessionStorage.setItem("learning-session-identifier", identifier);
  }
  let data = await postJson("/api/learning-sessions/start", { session_identifier: identifier });
  if (data.session.status !== "in_progress") {
    identifier = createRequestKey();
    sessionStorage.setItem("learning-session-identifier", identifier);
    data = await postJson("/api/learning-sessions/start", { session_identifier: identifier });
  }
  cachedSessionIdentifier = identifier;
  return data.session;
}

export async function getLearningSessionIdentifier() {
  if (cachedSessionIdentifier) return cachedSessionIdentifier;
  const session = await startLearningSession();
  return session.identifier;
}

function activityRequestStorageKey(sessionIdentifier, operationType, difficultyLevel) {
  const difficultySuffix = difficultyLevel === "standard" ? "" : `:${difficultyLevel}`;
  return `learning-activity-request:${sessionIdentifier}:${operationType}${difficultySuffix}`;
}

export async function startStudentActivity(operationType, difficultyLevel = "standard") {
  const sessionIdentifier = await getLearningSessionIdentifier();
  const storageKey = activityRequestStorageKey(sessionIdentifier, operationType, difficultyLevel);
  let requestKey = sessionStorage.getItem(storageKey);
  if (!requestKey) {
    requestKey = createRequestKey();
    sessionStorage.setItem(storageKey, requestKey);
  }
  const data = await postJson("/api/student-activities/start", {
    operation_type: operationType,
    difficulty_level: difficultyLevel,
    session_identifier: sessionIdentifier,
    request_key: requestKey,
  });
  sessionStorage.setItem(`learning-activity-id:${operationType}`, String(data.activity.id));
  return data.activity;
}

export async function completeStudentActivity(operationType, activityId, difficultyLevel = "standard") {
  const data = await postJson(`/api/student-activities/${activityId}/complete`, {});
  const sessionIdentifier = await getLearningSessionIdentifier();
  sessionStorage.removeItem(activityRequestStorageKey(sessionIdentifier, operationType, difficultyLevel));
  sessionStorage.removeItem(`learning-activity-id:${operationType}`);
  sessionStorage.removeItem(`activity-current-problem-${operationType}`);
  return data.activity;
}

export function getActiveActivityId(operationType) {
  const id = sessionStorage.getItem(`learning-activity-id:${operationType}`);
  return id ? Number(id) : null;
}

export function generateQuestion(operation, activityAttemptId) {
  if (!activityAttemptId) throw new Error("Activity tracking is still starting");
  return postJson(`/api/student-activities/${activityAttemptId}/questions`, {});
}

export function getNumberIdentificationQuestion(activityAttemptId) {
  if (!activityAttemptId) throw new Error("Activity tracking is still starting");
  return postJson(`/api/student-activities/${activityAttemptId}/number-questions`, {});
}

export function markQuestionDisplayed(questionId) {
  return postJson(`/api/learning-questions/${questionId}/displayed`, {});
}

export function submitLearningAnswer(questionId, payload) {
  return postJson(`/api/student-question-attempts/${questionId}`, payload);
}

export function getQuestionSubmissionKey(questionId) {
  const key = `learning-question-submit:${questionId}`;
  let value = sessionStorage.getItem(key);
  if (!value) {
    value = createRequestKey();
    sessionStorage.setItem(key, value);
  }
  return value;
}

export function clearQuestionSubmissionKey(questionId) {
  sessionStorage.removeItem(`learning-question-submit:${questionId}`);
}

export function recordRecognition(payload) {
  return postJson("/api/student-recognition-logs", payload);
}

export function getQuestionAttemptHistory(page = 1) {
  return requestJson(`/api/student-question-attempts?page=${page}&page_size=100`);
}

export function getActivityHistory(page = 1) {
  return requestJson(`/api/student-activities/history?page=${page}&page_size=100`);
}

export async function getPersonalizedDashboard(studentId) {
  const query = studentId ? `?student_id=${encodeURIComponent(studentId)}` : "";
  const data = await requestJson(`/api/personalized-learning/dashboard${query}`);
  const weeklyProgress = data?.weekly_progress;
  if (
    !data?.summary
    || !weeklyProgress
    || typeof weeklyProgress !== "object"
    || !Array.isArray(weeklyProgress.days)
    || typeof weeklyProgress.total_attempts !== "number"
  ) {
    throw new Error(
      "Dashboard response is incomplete. Restart the backend and refresh the page.",
    );
  }
  return data;
}

export function getAssignedStudents() {
  return requestJson("/api/personalized-learning/students");
}

export function predictNumber(videoBase64) {
  if (!videoBase64 || videoBase64.length < 1000) {
    throw new Error("Video too short or invalid");
  }
  return postJson("/predict-number", { video: videoBase64 });
}
