import { importLibrary, setOptions } from "@googlemaps/js-api-loader";
import { useEffect, useRef, useState } from "react";
import { FieldInput } from "./ui/Field";

export interface SelectedPlace {
  address: string;
  lat: number;
  lon: number;
}

interface AddressAutocompleteProps {
  value: string;
  onChange: (value: string) => void;
  onPlaceSelect?: (place: SelectedPlace) => void;
  placeholder?: string;
  required?: boolean;
  apiKey: string | null;
}

let loaderPromise: Promise<typeof google.maps.places> | null = null;
let loaderKey: string | null = null;

function loadPlacesLibrary(apiKey: string): Promise<typeof google.maps.places> {
  if (loaderPromise && loaderKey === apiKey) {
    return loaderPromise;
  }
  loaderKey = apiKey;
  setOptions({ key: apiKey, v: "weekly" });
  loaderPromise = importLibrary("places") as Promise<typeof google.maps.places>;
  return loaderPromise;
}

export function AddressAutocomplete({
  value,
  onChange,
  onPlaceSelect,
  placeholder,
  required,
  apiKey,
}: AddressAutocompleteProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const elRef = useRef<google.maps.places.PlaceAutocompleteElement | null>(null);
  const onChangeRef = useRef(onChange);
  const onPlaceSelectRef = useRef(onPlaceSelect);
  const [ready, setReady] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  onChangeRef.current = onChange;
  onPlaceSelectRef.current = onPlaceSelect;

  useEffect(() => {
    if (!apiKey) {
      setReady(false);
      setLoadError(null);
      return;
    }
    let cancelled = false;
    setLoadError(null);
    void loadPlacesLibrary(apiKey)
      .then(() => {
        if (!cancelled) {
          setReady(true);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setReady(false);
          setLoadError("Address suggestions unavailable right now.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [apiKey]);

  useEffect(() => {
    if (!ready || !apiKey || !hostRef.current) {
      return;
    }
    const host = hostRef.current;
    const { PlaceAutocompleteElement } = google.maps.places;
    const el = new PlaceAutocompleteElement({
      includedRegionCodes: ["us"],
      placeholder: placeholder ?? "Start typing your US address…",
      requestedRegion: "us",
    });
    el.className = "jd-place-autocomplete";
    el.value = value;
    if (required) {
      el.setAttribute("required", "");
    }
    host.replaceChildren(el);
    elRef.current = el;

    const onInput = () => {
      onChangeRef.current(el.value);
    };

    const onSelect = (event: Event) => {
      void (async () => {
        const prediction = (event as google.maps.places.PlacePredictionSelectEvent).placePrediction;
        if (!prediction) {
          return;
        }
        const place = prediction.toPlace();
        try {
          await place.fetchFields({
            fields: ["formattedAddress", "location", "displayName"],
          });
        } catch {
          setLoadError("Could not load that address. Try another suggestion.");
          return;
        }
        const formatted =
          place.formattedAddress ?? place.displayName ?? el.value ?? "";
        el.value = formatted;
        onChangeRef.current(formatted);
        const location = place.location;
        const select = onPlaceSelectRef.current;
        if (location && select) {
          select({
            address: formatted,
            lat: location.lat(),
            lon: location.lng(),
          });
        }
      })();
    };

    const onError = () => {
      setLoadError("Address suggestions could not load on this page.");
    };

    el.addEventListener("input", onInput);
    el.addEventListener("gmp-select", onSelect);
    el.addEventListener("gmp-error", onError);

    return () => {
      el.removeEventListener("input", onInput);
      el.removeEventListener("gmp-select", onSelect);
      el.removeEventListener("gmp-error", onError);
      el.remove();
      elRef.current = null;
      host.replaceChildren();
    };
    // Intentionally omit `value` — synced in a separate effect so the widget is not recreated on each keystroke.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, apiKey, placeholder, required]);

  useEffect(() => {
    const el = elRef.current;
    if (el && value !== el.value) {
      el.value = value;
    }
  }, [value]);

  if (!apiKey || !ready) {
    return (
      <div>
        <FieldInput
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder={placeholder}
          required={required}
          autoComplete="street-address"
        />
        {!apiKey ? (
          <p className="mt-1.5 text-xs text-subtle">
            Address suggestions are offline (Maps key not loaded). You can still type an address.
          </p>
        ) : null}
        {loadError ? <p className="mt-1.5 text-xs text-danger">{loadError}</p> : null}
      </div>
    );
  }

  return (
    <div>
      <div ref={hostRef} className="jd-place-autocomplete-host mt-1.5" />
      {loadError ? <p className="mt-1.5 text-xs text-danger">{loadError}</p> : null}
    </div>
  );
}
