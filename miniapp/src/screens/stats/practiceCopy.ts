import { addMessages } from "../../i18n/lazyMessages";
import en from "../../locales/en/practice.ftl?raw";
import ru from "../../locales/ru/practice.ftl?raw";

// UI-06 stage 3: the Practice tab's own copy comes with its lazy chunk, not with the first
// one. Imported for this effect by every module that shows one of these messages.
addMessages({ en, ru });
