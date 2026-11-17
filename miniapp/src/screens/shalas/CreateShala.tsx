import { Localized, useLocalization } from "@fluent/react";
import { useEffect, useRef, useState, type SyntheticEvent } from "react";

import { ApiError, useCreateShala, useMe, useMoonCities } from "../../api/client";
import type { Locale } from "../../i18n/negotiate";
import { haptics } from "../../telegram";
import { Field, Select, TextInput } from "../../ui/controls";
import { cityName } from "../cityName";

const NAME_MAX = 64;

interface Props {
  /** The new shala's id: its card opens, with the setup list. */
  onDone: (id: string) => void;
  /** Opened for this (the bot's "Create a shala"): the name takes the focus. */
  focus: boolean;
}

/** A new shala in two fields (SC-01, UI-06 stage 4): its name and its city, which sets the
 * zone and the moon days. The owner starts as its teacher; online-only, the moon city, the day
 * off and the owner's own roles are changed afterwards on the card (Q338). */
export default function CreateShala({ onDone, focus }: Props) {
  const { l10n } = useLocalization();
  const first = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (focus) first.current?.focus();
  }, [focus]);
  const me = useMe().data;
  const cities = useMoonCities().data;
  const create = useCreateShala();
  const locale: Locale = me?.locale ?? "en";
  const [name, setName] = useState("");
  const [city, setCity] = useState<string | null>(null);
  const [blank, setBlank] = useState(false);
  const chosen = city ?? me?.home_city?.slug ?? cities?.[0]?.slug ?? "";
  const submit = (e: SyntheticEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setBlank(true);
      haptics.notify("error");
      first.current?.focus();
      return;
    }
    setBlank(false);
    haptics.impact("light");
    create.mutate(
      { name, city: chosen, online: false, roles: ["teacher"] },
      {
        onSuccess: (shala) => {
          onDone(shala.id);
        },
        onError: () => {
          haptics.notify("error");
        },
      },
    );
  };
  const capped = create.error instanceof ApiError && create.error.code === "shala_caps";
  const badName =
    blank || (create.error instanceof ApiError && create.error.code === "invalid_shala_name");
  return (
    <form className="panel" noValidate onSubmit={submit}>
      <Field
        label={l10n.getString("shala-name-label")}
        error={badName && l10n.getString("shala-name-invalid")}
      >
        <TextInput
          ref={first}
          value={name}
          maxLength={NAME_MAX}
          onChange={(e) => {
            setName(e.target.value);
          }}
        />
      </Field>
      <Field label={l10n.getString("shala-city-label")}>
        <Select
          value={chosen}
          onChange={(e) => {
            setCity(e.target.value);
          }}
        >
          {cities?.map((c) => (
            <option key={c.slug} value={c.slug}>
              {cityName(c, c.slug, locale)}
            </option>
          ))}
        </Select>
      </Field>
      <Localized id="shala-create-submit">
        <button type="submit" className="btn" disabled={create.isPending} />
      </Localized>
      {create.isError && !badName && (
        <Localized id={capped ? "shala-caps" : "shala-save-failed"}>
          <p className="hint" role="alert" />
        </Localized>
      )}
    </form>
  );
}
