import { Localized } from "@fluent/react";

import { useDismissDayOffQuestion, useNotificationSettings, useSetDayOff } from "../api/client";
import { haptics } from "../telegram";

/** The one-time "is that your day off?" (PR-09): only while the day off was never chosen
 * and reminders skip exactly one weekday (the server decides). Never in a push. */
export function DayOffQuestion({ onOther }: { onOther: () => void }) {
  const question = useNotificationSettings().data?.day_off_question;
  const setDayOff = useSetDayOff();
  const dismiss = useDismissDayOffQuestion();
  if (!question) return null;
  const { weekday } = question;
  const other = weekday === 6 ? 7 : weekday === 7 ? 6 : null; // the other weekend day
  const choose = (d: number) => {
    haptics.impact("light");
    setDayOff.mutate([d]);
  };
  return (
    <div className="question" role="group" aria-labelledby="day-off-ask">
      <Localized
        id="day-off-ask"
        vars={{ d: weekday, reminders: question.reminders_on ? "on" : "off" }}
      >
        <p id="day-off-ask" />
      </Localized>
      <div className="chips">
        <Localized id="day-off-ask-yes">
          <button
            type="button"
            className="chip"
            onClick={() => {
              choose(weekday);
            }}
          />
        </Localized>
        {other !== null && (
          <Localized id="day-off-ask-instead" vars={{ d: other }}>
            <button
              type="button"
              className="chip"
              onClick={() => {
                choose(other);
              }}
            />
          </Localized>
        )}
        <Localized id="day-off-ask-other">
          <button type="button" className="chip" onClick={onOther} />
        </Localized>
        <Localized id="day-off-ask-later">
          <button
            type="button"
            className="chip"
            onClick={() => {
              dismiss.mutate();
            }}
          />
        </Localized>
      </div>
    </div>
  );
}
