import type { GoalProfile, Seniority } from "@contracts/types";

const GOAL_PROFILE_KEY = "profilepilot:goal_profile";
const INTAKE_DRAFT_KEY = "profilepilot:intake_draft";

export type IntakeDraft = Partial<Omit<GoalProfile, "seniority">> & {
  seniority?: Seniority | "";
  step?: number;
};

export function saveGoalProfile(profile: GoalProfile): void {
  sessionStorage.setItem(GOAL_PROFILE_KEY, JSON.stringify(profile));
}

export function loadGoalProfile(): GoalProfile | null {
  const raw = sessionStorage.getItem(GOAL_PROFILE_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as GoalProfile;
  } catch {
    return null;
  }
}

export function saveIntakeDraft(draft: IntakeDraft): void {
  sessionStorage.setItem(INTAKE_DRAFT_KEY, JSON.stringify(draft));
}

export function loadIntakeDraft(): IntakeDraft | null {
  const raw = sessionStorage.getItem(INTAKE_DRAFT_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as IntakeDraft;
  } catch {
    return null;
  }
}

export function clearIntakeDraft(): void {
  sessionStorage.removeItem(INTAKE_DRAFT_KEY);
}
