import { useMutation, useQueries, useQueryClient } from "@tanstack/react-query";

import {
  api,
  fail,
  LINKS_KEY,
  NEXT_STEPS_KEY,
  STUDENTS_KEY,
  type ApprovedAll,
  type AskedTeacher,
  type StudentRequest,
  type StudentRequests,
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

export type { AskedTeacher, StudentRequest, StudentRequests };

/** The API's largest page. */
export const REQUESTS_PAGE = 50;

const REQUESTS_KEY = ["student-requests"];

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

/** The student takes a request back. The answer is the same whether anything was waiting. */
export function useWithdrawRequest() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (teacherId: string): Promise<void> => {
      const { error, response } = await api.DELETE("/api/v1/me/teacher-requests/{teacher_id}", {
        params: { path: { teacher_id: teacherId } },
      });
      if (!response.ok) fail(response, error);
    },
    onSettled: () => client.invalidateQueries({ queryKey: LINKS_KEY }),
  });
}
