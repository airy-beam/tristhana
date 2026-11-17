// The day card's two panels (UI-06): practice details and the check-in editor, with their
// copy (`details.ftl`). One lazy chunk, loaded when the card first shows a practiced day and
// mounted only on a tap.
import { addMessages } from "../i18n/lazyMessages";
import enDetails from "../locales/en/details.ftl?raw";
import ruDetails from "../locales/ru/details.ftl?raw";

addMessages({ en: enDetails, ru: ruDetails });

export { CheckIn } from "./CheckIn";
export { PracticeDetails } from "./PracticeDetails";
