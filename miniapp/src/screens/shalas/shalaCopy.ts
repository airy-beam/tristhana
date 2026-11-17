import { addMessages } from "../../i18n/lazyMessages";
import en from "../../locales/en/shala.ftl?raw";
import ru from "../../locales/ru/shala.ftl?raw";

// UI-06 stage 4: the copy of the class form, the occurrence sheet's groups and the setup list
// comes with the shala card's lazy chunk, not with the first one. Imported for this effect by
// every module that shows one of these messages.
addMessages({ en, ru });
