import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  api,
  ApiError,
  fail,
  LINKS_KEY,
  NEXT_STEPS_KEY,
  STUDENTS_KEY,
  type ApprovedAll,
  type AskBody,
  type AskedTeacher,
  type AskResult,
  type StudentRequest,
  type StudentRequests,
  type TeacherChoice,
  type TeacherChoices,
} from "../../api/client";
import { addMessages } from "../../i18n/lazyMessages";
import en from "../../locales/en/requests.ftl?raw";
import ru from "../../locales/ru/requests.ftl?raw";
import "./requests.css";

// ID-07: teacher requests. A student names a teacher in the bot; the teacher answers here or
// there, and the student can withdraw. Kept out of api/client, with its copy (`requests.ftl`)
// and its styles, so the first chunk carries none of it: only the lazy Shala tab chunks import
// this. Writes wait for the server.
addMessages({ en, ru });

export type { AskedTeacher, AskResult, StudentRequest, StudentRequests, TeacherChoice };

/** The API's largest page. */
export const REQUESTS_PAGE = 50;

const REQUESTS_KEY = ["student-requests"];
/** Who a student can ask in a shala, one key per shala (UI-06 stage 4B). */
const CHOICES_KEY = ["teacher-choices"];
/** `useMyShalas`'s key (api/client): a 404 on the ask means I left the shala meanwhile. */
const MY_SHALAS_KEY = ["shalas", "mine"];

/** The people waiting for my answer, oldest first, one query per page shown. The first page's
 * `as_of` is the moment "Confirm all" sends back. */
export function useStudentRequests(pages: number) {
  return useQueries({
    queries: Array.from({ length: pages }, (_, n) => ({
      staleTime: 60_000,
      queryKey: [...REQUESTS_KEY, n * REQUESTS_PAGE],
      queryFn: async (): Promise<StudentRequests> => {
        const { data, error, response } = await api.GET("/api/v1/me/student-requests", {
          params: { query: { offset: n * REQUESTS_PAGE, limit: REQUESTS_PAGE } },
        });
        if (!data) fail(response, error);
        return data;
      },
    })),
  });
}

export type Answer = "approve" | "decline" | "reopen";

const ANSWERS = {
  approve: "/api/v1/me/student-requests/{student_id}/approve",
  decline: "/api/v1/me/student-requests/{student_id}/decline",
  reopen: "/api/v1/me/student-requests/{student_id}/reopen",
} as const;

/** What an answer can change: who waits (here and in the Shala tab's count) and, after a yes,
 * my students and the "invite your first student" step. Refetched after a failure too: a 404
 * means the list on screen is out of date. No moon change: an approver is on a shala's staff
 * and follows it with or without students (MD-02). */
function useRefresh() {
  const client = useQueryClient();
  return (linked: boolean) => {
    if (linked) {
      void client.invalidateQueries({ queryKey: STUDENTS_KEY });
      void client.invalidateQueries({ queryKey: NEXT_STEPS_KEY });
    }
    void client.invalidateQueries({ queryKey: LINKS_KEY });
    return client.invalidateQueries({ queryKey: REQUESTS_KEY });
  };
}

/** "Yes, my student", "Not my student" and its Undo. 404 `request_gone`: no longer open, for
 * whatever reason; 409 `list_full` (a yes only): the request stays waiting. `onAnswered` runs
 * as soon as the server says yes, before the list is read again; the callbacks given to
 * `mutate` run after that read. */
export function useAnswerRequest(onAnswered: (sent: { id: string; answer: Answer }) => void) {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: async ({ id, answer }: { id: string; answer: Answer }): Promise<void> => {
      const { error, response } = await api.POST(ANSWERS[answer], {
        params: { path: { student_id: id } },
      });
      if (!response.ok) fail(response, error);
    },
    onSuccess: (_data, sent) => {
      onAnswered(sent);
    },
    onSettled: (_data, _error, { answer }) => refresh(answer === "approve"),
  });
}

/** "Confirm all": everyone who was waiting at `asOf`, the moment the list on screen was drawn,
 * so someone who asked a second later is never confirmed unseen. */
export function useApproveAll() {
  const refresh = useRefresh();
  return useMutation({
    mutationFn: async (asOf: string): Promise<ApprovedAll> => {
      const { data, error, response } = await api.POST("/api/v1/me/student-requests/approve-all", {
        body: { as_of: asOf },
      });
      if (!data) fail(response, error);
      return data;
    },
    onSettled: () => refresh(true),
  });
}

/** The student takes a request back. The answer is the same whether anything was waiting. The
 * waiting lines and who can be picked are read again, here and on every shala's card. */
export function useWithdrawRequest() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (teacherId: string): Promise<void> => {
      const { error, response } = await api.DELETE("/api/v1/me/teacher-requests/{teacher_id}", {
        params: { path: { teacher_id: teacherId } },
      });
      if (!response.ok) fail(response, error);
    },
    onSettled: () =>
      Promise.all([
        client.invalidateQueries({ queryKey: LINKS_KEY }),
        client.invalidateQueries({ queryKey: CHOICES_KEY }),
      ]),
  });
}

// UI-06 stage 4B (spec §4, ADR-0049): asking a teacher of my shala from the app.

/** The one line an ask or a withdraw leaves on the screen it was done from (QE): the bot's
 * words, already formatted; `alert` when it could not be done. */
export interface Said {
  text: string;
  alert?: boolean;
}

/** Who I can ask in a shala and who I wait for there (oldest staff first). One cache key per
 * shala, shared by the Shala tab, the shala's card and the picker. Read only for a student of
 * that shala: staff and a former member get one 404. An older API answers without the lists. */
function choicesQuery(shala: string) {
  return {
    staleTime: 60_000,
    queryKey: [...CHOICES_KEY, shala],
    queryFn: async (): Promise<TeacherChoices> => {
      const { data, error, response } = await api.GET("/api/v1/shalas/{id}/teacher-choices", {
        params: { path: { id: shala } },
      });
      if (!data) fail(response, error);
      const read: Partial<TeacherChoices> = data;
      return { offer: read.offer ?? [], waiting: read.waiting ?? [] };
    },
  };
}

export function useTeacherChoices(shala: string, enabled: boolean) {
  return useQuery({ ...choicesQuery(shala), enabled });
}

/** The same, for each shala I am a student of (the Shala tab's "🤝 Pick a teacher", QA). */
export function useTeacherChoicesOf(shalas: string[]) {
  return useQueries({ queries: shalas.map(choicesQuery) });
}

/** The consent the picker shows: the bot's `request-consent` and its short layer. The server
 * decides what it grants; a change of promises is a new value (ADR-0049). */
const CONSENT: AskBody["consent"] = "request-1";

/** A tap on a name: the consent and the request at once. Not optimistic: the result is the
 * server's, already projected (a quiet "no" reads as `waiting` or `recent`, as silence does).
 * Afterwards who I wait for and who can be picked are read again; after a 404 (no longer a
 * student there), my shalas too. The callbacks given to `mutate` run after those reads. */
export function useAskTeacher() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({ shala, teacher }: { shala: string; teacher: string }) => {
      const { data, error, response } = await api.POST("/api/v1/me/teacher-requests", {
        body: { shala_id: shala, teacher_id: teacher, consent: CONSENT },
      });
      if (!data) fail(response, error);
      return data.result;
    },
    onSettled: (_data, error, { shala }) =>
      Promise.all([
        client.invalidateQueries({ queryKey: LINKS_KEY }),
        client.invalidateQueries({ queryKey: [...CHOICES_KEY, shala] }),
        error instanceof ApiError && error.status === 404
          ? client.invalidateQueries({ queryKey: MY_SHALAS_KEY })
          : undefined,
      ]),
  });
}
