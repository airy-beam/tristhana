"""Teacher requests in the bot (ID-07, ADR-0046): a student of a shala names their teacher,
the teacher says yes.

The student's side hangs off the shala (`h1:t…`): the question after joining and from the
card, the consent behind "Details", the waiting line and Withdraw. The teacher's side hangs
off "My students" (`t1:r…`): the note with Yes and "Not my student", one request's screen,
the waiting list and "Confirm all".

Nothing here decides anything: every tap calls a use case and shows what it returned. The
student never reads a "no": `AskState.FULL` says only "not right now", a quiet no looks like
waiting, and the teacher's answer reaches the student only through the tick's closing note.
An id in callback data is no capability: every write is keyed on the caller.
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from tristhana.application.policies import NotAllowed, NotFound, Principal
from tristhana.application.ports.i18n import Translator
from tristhana.application.ports.notifications import TeacherAsked
from tristhana.application.ports.teacher_requests import (
    Answer,
    Answered,
    CardRequests,
    Choices,
)
from tristhana.application.teacher_requests import RequestUseCases
from tristhana.bots.telegram import shalas_callbacks as shala_cb
from tristhana.bots.telegram import teacher_links_callbacks as cb
from tristhana.bots.telegram.screens import Screen, button
from tristhana.domain.accounts import Account
from tristhana.domain.locale import Locale
from tristhana.domain.teacher_links import shown_name
from tristhana.domain.teacher_requests import AskState

if TYPE_CHECKING:
    from tristhana.bots.telegram.shalas import ShalaScreens
    from tristhana.bots.telegram.start import StartScreens
    from tristhana.bots.telegram.teacher_links import LinkScreens

PAGE = 10
# ADR-0031: the request stores the quiet-note consent of the screen that was tapped, and the
# approval copies it. Both layers of `request-consent` name the note and share one confirm,
# `h1:ta`, so that tap always agrees to it (pinned in `test_i18n_teacher_requests.py`). A
# later consent item gets a new callback letter, never a new meaning for this one.
QUIET_NOTE_AGREED = True

# What the student's tap came to, as one line above Today. No line says or implies a "no".
_ASKED: dict[AskState, str] = {
    AskState.CREATED: "request-asked",
    AskState.LINKED: "invite-already",
    AskState.WAITING: "request-waiting",
    AskState.RECENT: "request-recent",
    AskState.TOO_MANY: "request-too-many",
    AskState.FULL: "request-full",
}


def _name(t: Translator, locale: Locale, name: str | None) -> str:
    return shown_name(name) or t.t(locale, "link-no-name")


def _counted(
    t: Translator, locale: Locale, key: str, count: int, data: str
) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=t.t(locale, key, count=count), callback_data=data)


def waiting_row(t: Translator, locale: Locale, count: int) -> list[InlineKeyboardButton]:
    """`[⏳ Waiting for your answer (N)]` on "My students" and on the teacher's shala card."""
    return [_counted(t, locale, "request-waiting-open", count, cb.waiting(0))]


def request_note(
    t: Translator,
    locale: Locale,
    student_id: UUID,
    student_name: str | None,
    shala_name: str,
    waiting: int,
    back: bool = False,
) -> Screen:
    """One request, as the teacher reads it: the note sent at the student's tap, and the same
    screen opened from the waiting list (`back`: with a way back to it). "See all" only from
    two, this one included."""
    text = t.t(locale, "request-note", student=_name(t, locale, student_name), shala=shala_name)
    rows = [
        [
            button(t, locale, "request-yes-mine", cb.person("ra", student_id)),
            button(t, locale, "request-not-mine", cb.person("rn", student_id)),
        ]
    ]
    if waiting >= 2:
        rows.append([_counted(t, locale, "request-see-all", waiting, cb.waiting(0))])
    elif back:
        rows.append([button(t, locale, "log-back", cb.waiting(0))])
    return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))


def asked_note(t: Translator, locale: Locale, asked: TeacherAsked) -> Screen:
    """The teacher's note at the student's tap, in the teacher's language."""
    return request_note(
        t, locale, asked.student_id, asked.student_name, asked.shala_name, asked.waiting
    )


class RequestScreens:
    def __init__(
        self,
        requests: RequestUseCases,
        start: "StartScreens",
        links: "LinkScreens",
        translator: Translator,
        bot_username: str,
    ) -> None:
        self._r = requests
        self._start = start
        self._links = links
        self._t = translator
        self._username = bot_username
        self.shalas: ShalaScreens | None = None  # set by the router: the card is theirs

    def _button(self, locale: Locale, key: str, data: str) -> InlineKeyboardButton:
        return button(self._t, locale, key, data)

    def _named(self, locale: Locale, key: str, name: str | None, data: str) -> InlineKeyboardButton:
        text = self._t.t(locale, key, name=_name(self._t, locale, name))
        return InlineKeyboardButton(text=text, callback_data=data)

    async def _card(
        self,
        principal: Principal,
        shala: UUID,
        note: str | None = None,
        asked: Choices | None = None,
    ) -> Screen:
        if self.shalas is None:
            return await self._links.overview(principal)
        return await self.shalas.card(principal, shala, note, asked)

    # The student's side

    async def choices(self, principal: Principal, shala: UUID) -> Choices | None:
        """Who can be asked in `shala` and who I wait for; None when I am not a student
        there (staff, left, or a forged id)."""
        try:
            return await self._r.choices.execute(principal, shala)
        except NotFound:
            return None

    async def beside_card(self, principal: Principal, shala: UUID) -> CardRequests:
        """The requests part of the shala card, read beside it: the student's choices
        there, or how many wait for a teacher of it (in every shala)."""
        return await self._r.card.execute(principal, shala)

    def card_parts(
        self, locale: Locale, found: Choices
    ) -> tuple[list[str], list[list[InlineKeyboardButton]]]:
        """The student's part of the shala card: one line per teacher I wait for, the row
        that opens the question while someone can be asked, and a Withdraw row per line."""
        lines = [
            self._t.t(locale, "request-waiting-line", name=_name(self._t, locale, w.name))
            for w in found.waiting
        ]
        rows: list[list[InlineKeyboardButton]] = []
        if found.offer:
            rows.append(
                [self._button(locale, "request-open", shala_cb.on_shala("t", found.shala_id))]
            )
        for w in found.waiting:
            data = shala_cb.on_member("tw", found.shala_id, w.id)
            rows.append([self._named(locale, "request-withdraw", w.name, data)])
        return lines, rows

    def question(
        self, account: Account, found: Choices, details: bool = False, note: str | None = None
    ) -> Screen:
        """ "Who is your teacher here?": the short consent, or the full text behind
        "Details" (ADR-0045). The full text is the consent record; a name on either screen
        is the same tap and agrees to all of it."""
        locale = account.locale
        own = shown_name(account.display_name)
        me = f" ({own})" if own else ""
        shala = found.shala_id
        if len(found.offer) == 1:
            only = found.offer[0]
            ask = self._t.t(locale, "request-ask-one", name=_name(self._t, locale, only.name))
            picks = [
                [self._button(locale, "request-yes", shala_cb.on_member("ta", shala, only.id))]
            ]
        else:
            ask = self._t.t(locale, "request-ask")
            picks = [
                [
                    InlineKeyboardButton(
                        text=_name(self._t, locale, teacher.name),
                        callback_data=shala_cb.on_member("ta", shala, teacher.id),
                    )
                ]
                for teacher in found.offer
            ]
        parts = [f"🏛 {found.shala_name}\n{ask}"]
        not_now = self._button(locale, "invite-decline", shala_cb.on_shala("tn", shala))
        if details:
            parts.append(self._t.t(locale, "request-consent", me=me))
            layer = self._button(locale, "consent-short-back", shala_cb.on_shala("t", shala))
        else:
            parts.append(self._t.t(locale, "request-consent-short", me=me))
            parts.append(self._t.t(locale, "request-until-yes"))
            layer = self._button(locale, "consent-details", shala_cb.on_shala("td", shala))
        parts.append(self._t.t(locale, "request-know-them"))
        if note:
            parts.append(note)
        rows = [*picks, [layer, not_now]]
        return Screen("\n\n".join(parts), InlineKeyboardMarkup(inline_keyboard=rows))

    async def ask_screen(self, principal: Principal, shala: UUID, details: bool = False) -> Screen:
        """`h1:t` / `h1:td`: the question, or the card when there is nobody to ask (with a
        line saying so) or I am not a student there."""
        found = await self.choices(principal, shala)
        if found is None:
            return await self._card(principal, shala)
        if not found.offer:
            nobody = self._t.t(principal.account.locale, "request-nobody")
            return await self._card(principal, shala, nobody, found)
        return self.question(principal.account, found, details)

    async def ask(self, principal: Principal, shala: UUID, teacher: UUID) -> Screen:
        """`h1:ta`, the consent tap: Today with one line on top, whatever it came to."""
        locale = principal.account.locale
        try:
            asked = await self._r.ask.execute(
                principal, shala, teacher, quiet_note_agreed=QUIET_NOTE_AGREED
            )
        except NotFound:  # left the shala since the screen was drawn
            return await self._links.overview(principal)
        except NotAllowed:  # an old name: no longer a teacher there, or I am staff now
            return await self.ask_screen(principal, shala)
        name = _name(self._t, locale, asked.teacher_name)
        return await self._start.start(principal, self._t.t(locale, _ASKED[asked.state], name=name))

    async def ask_withdraw(self, principal: Principal, shala: UUID, teacher: UUID) -> Screen:
        """`h1:tw`: one confirm step, naming the teacher."""
        locale = principal.account.locale
        found = await self.choices(principal, shala)
        waiting = next((w for w in found.waiting if w.id == teacher), None) if found else None
        if waiting is None:  # answered or withdrawn meanwhile: the card shows what is true
            return await self._card(principal, shala, asked=found)
        rows = [
            [
                self._button(
                    locale, "request-withdraw-yes", shala_cb.on_member("tx", shala, teacher)
                )
            ],
            [self._button(locale, "log-back", shala_cb.on_shala("c", shala))],
        ]
        text = self._t.t(locale, "request-withdraw-ask", name=_name(self._t, locale, waiting.name))
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))

    async def withdraw(self, principal: Principal, shala: UUID, teacher: UUID) -> Screen:
        """`h1:tx`: silent. Confirmed meanwhile: the teacher's card, where Remove is."""
        done = await self._r.withdraw.execute(principal, teacher)
        if done.linked:
            return await self._links.teacher(principal, teacher, already=True)
        note = self._t.t(principal.account.locale, "request-withdrawn") if done.removed else None
        return await self._card(principal, shala, note)

    # The teacher's side

    async def waiting_count(self, principal: Principal) -> int:
        """How many people wait for my answer, in every shala."""
        return (await self._r.mine.execute(principal)).waiting

    def _more(self, locale: Locale, waiting: int) -> list[list[InlineKeyboardButton]]:
        if waiting < 1:
            return []
        return [[_counted(self._t, locale, "request-see-all", waiting, cb.waiting(0))]]

    def _students_row(self, locale: Locale) -> list[InlineKeyboardButton]:
        return [self._button(locale, "link-students-open", cb.students(0))]

    def _closed(self, locale: Locale, answer: Answer) -> Screen:
        """A tap that changed nothing: already linked, a cap, or a request that is gone. Each
        screen keeps a way on: My students or the own link, and the rest of the list."""
        students = self._students_row(locale)
        first = students
        match answer.outcome:
            case Answered.ALREADY:  # the link wins; a "no" never removes it
                key = "request-already-student"
            case Answered.FULL:  # the request stays waiting
                key = "request-list-full"
            case _:  # one line for every reason, and the way out: the teacher's own link
                key = "request-gone"
                if self._username:
                    first = [self._button(locale, "links-invite", cb.plain("i"))]
        rows = [first, *self._more(locale, answer.waiting)]
        return Screen(self._t.t(locale, key), InlineKeyboardMarkup(inline_keyboard=rows))

    async def request(self, principal: Principal, student: UUID) -> Screen:
        """`t1:rv`: one request's screen, as the note showed it."""
        locale = principal.account.locale
        page = await self._r.waiting.execute(principal, 0, 1, student)
        if not page.requests:
            return self._closed(locale, Answer(Answered.GONE, waiting=page.total))
        found = page.requests[0]
        return request_note(
            self._t, locale, found.student_id, found.name, found.shala_name, page.total, back=True
        )

    async def approve(self, principal: Principal, student: UUID) -> Screen:
        """`t1:ra`, "Yes, my student": the link. The student's note is the tick's."""
        locale = principal.account.locale
        answer = await self._r.approve.execute(principal, student)
        if answer.outcome is not Answered.DONE:
            return self._closed(locale, answer)
        name = _name(self._t, locale, answer.student_name)
        rows = [self._students_row(locale), *self._more(locale, answer.waiting)]
        text = self._t.t(locale, "link-student-joined", name=name)
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))

    async def decline(self, principal: Principal, student: UUID) -> Screen:
        """`t1:rn`, "Not my student": the student isn't told. Undo works inside the 7 days."""
        locale = principal.account.locale
        answer = await self._r.decline.execute(principal, student)
        if answer.outcome is not Answered.DONE:
            return self._closed(locale, answer)
        name = _name(self._t, locale, answer.student_name)
        rows = [
            [self._button(locale, "request-undo", cb.person("ru", student))],
            *self._more(locale, answer.waiting),
            self._students_row(locale),
        ]
        text = self._t.t(locale, "request-declined", name=name)
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))

    async def undo(self, principal: Principal, student: UUID) -> Screen:
        """`t1:ru`: the request waits again, and its screen is back."""
        answer = await self._r.reopen.execute(principal, student)
        if answer.outcome is not Answered.DONE:
            return self._closed(principal.account.locale, answer)
        return await self.request(principal, student)

    def _empty(self, locale: Locale) -> Screen:
        rows = [[self._button(locale, "log-back", cb.students(0))]]
        text = self._t.t(locale, "request-list-empty")
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))

    async def waiting(self, principal: Principal, page: int) -> Screen:
        """`t1:rl`: the people waiting for my answer, oldest first."""
        locale = principal.account.locale
        found = await self._r.waiting.execute(principal, page * PAGE, PAGE)
        if not found.requests and page > 0:  # the list got shorter since the button was drawn
            page = 0
            found = await self._r.waiting.execute(principal, 0, PAGE)
        if not found.requests:
            return self._empty(locale)
        rows = [
            [
                InlineKeyboardButton(
                    text=f"{_name(self._t, locale, r.name)} · {r.shala_name}",
                    callback_data=cb.person("rv", r.student_id),
                )
            ]
            for r in found.requests
        ]
        last = max(0, (found.total - 1) // PAGE)
        turn: list[InlineKeyboardButton] = []
        if page > 0:
            turn.append(self._button(locale, "page-prev", cb.waiting(page - 1)))
        if page < last:
            turn.append(self._button(locale, "page-next", cb.waiting(page + 1)))
        if turn:
            rows.append(turn)
        # The moment this list was drawn, rounded down to the second: "Confirm all" takes
        # it through its confirm step unchanged, and confirms only who asked before it.
        drawn = int(found.as_of.timestamp())
        rows.append([_counted(self._t, locale, "request-all", found.total, cb.ask_all(drawn))])
        rows.append([self._button(locale, "log-back", cb.students(0))])
        text = "\n".join(
            [
                self._t.t(locale, "request-list-title", count=found.total),
                self._t.t(locale, "request-list-hint"),
            ]
        )
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))

    async def ask_all(self, principal: Principal, before: int) -> Screen:
        """`t1:rc:<unix>`: one confirm step. `before` is the moment the list was drawn, and
        the Yes carries it on unchanged: someone who asked since is on neither the list the
        teacher read nor in the count named here, and is not confirmed.

        The moment is whole seconds, rounded down, and the comparison is strict. So a
        request made in the list's own second is left waiting, whether it came just before
        the list (seen) or just after (unseen): the two can't be told apart, and leaving
        both is the safe side. It is not lost: it stays on the list, and the next list
        carries a later moment. With nobody to confirm for this moment, the list as it is
        now, with a fresh one."""
        locale = principal.account.locale
        found = await self._r.waiting.execute(
            principal, 0, 1, before=datetime.fromtimestamp(before, UTC)
        )
        if found.total == 0:
            return await self.waiting(principal, 0)
        rows = [
            [self._button(locale, "request-all-yes", cb.confirm_all(before))],
            [self._button(locale, "log-back", cb.waiting(0))],
        ]
        text = self._t.t(locale, "request-all-ask", count=found.total)
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))

    async def confirm_all(self, principal: Principal, before: int) -> Screen:
        """`t1:rcy`: confirms who is still waiting and asked before that moment (the list's,
        see `ask_all`); the reply says how many, and the rest stay on the list."""
        locale = principal.account.locale
        done = await self._r.approve_all.execute(principal, datetime.fromtimestamp(before, UTC))
        if done.approved == 0:  # an old button: the list as it is now
            return await self.waiting(principal, 0) if done.left else self._empty(locale)
        rows = [self._students_row(locale), *self._more(locale, done.left)]
        text = self._t.t(locale, "request-all-done", count=done.approved)
        return Screen(text, InlineKeyboardMarkup(inline_keyboard=rows))
