"use client";

import { useCallback, useEffect, useState } from "react";
import type { FieldNode } from "@/lib/settings-form";
import { colorTextDomId, fieldDomId } from "@/lib/settings-form";

type SettingsFieldProps = {
  node: FieldNode;
  onBrowsePath?: (inputId: string, currentValue: string) => void;
};

function RenderGroup({
  node,
  onBrowsePath,
}: {
  node: Extract<FieldNode, { kind: "group" }>;
  onBrowsePath?: SettingsFieldProps["onBrowsePath"];
}) {
  if (node.children.length === 0) {
    return (
      <fieldset className="settings-group settings-group--empty">
        {node.label ? <legend className="settings-group__legend">{node.label}</legend> : null}
        <p className="settings-field__hint">
          Empty — add entries via the advanced editor below.
        </p>
      </fieldset>
    );
  }

  return (
    <fieldset
      className={`settings-group settings-group--depth-${node.depth}${
        node.is_bool_only ? " settings-group--toggles" : ""
      }`}
    >
      {node.depth > 0 && node.label ? (
        <legend className="settings-group__legend">{node.label}</legend>
      ) : null}
      <div className="settings-group__children">
        {node.children.map((child) => (
          <SettingsField key={child.name} node={child} onBrowsePath={onBrowsePath} />
        ))}
      </div>
    </fieldset>
  );
}

function ColorFieldInput({
  node,
}: {
  node: Extract<FieldNode, { kind: "color" }>;
}) {
  const pickerId = fieldDomId(node.name);
  const textId = colorTextDomId(node.name);
  const [hex, setHex] = useState(node.value);

  useEffect(() => {
    setHex(node.value);
  }, [node.value]);

  const onPickerChange = useCallback((value: string) => {
    setHex(value.toUpperCase());
  }, []);

  const onTextChange = useCallback((value: string) => {
    setHex(value);
    const trimmed = value.trim();
    if (/^#[0-9a-fA-F]{6}$/.test(trimmed)) {
      setHex(trimmed.toUpperCase());
    }
  }, []);

  const onTextBlur = useCallback(() => {
    if (!/^#[0-9a-fA-F]{6}$/.test(hex.trim())) {
      setHex(node.value);
    }
  }, [hex, node.value]);

  const pickerValue = /^#[0-9a-fA-F]{6}$/.test(hex.trim()) ? hex.trim() : node.value;

  return (
    <div className="settings-field settings-field--color">
      <label className="settings-field__label" htmlFor={pickerId}>
        {node.label}
        <code className="settings-field__path">{node.name}</code>
      </label>
      <div className="color-input">
        <input
          className="color-input__picker"
          id={pickerId}
          name={node.name}
          type="color"
          value={pickerValue}
          onChange={(e) => onPickerChange(e.target.value)}
        />
        <input
          className="color-input__text input"
          id={textId}
          type="text"
          value={hex}
          maxLength={7}
          pattern="^#[0-9a-fA-F]{6}$"
          aria-label={`${node.label} hex value`}
          onChange={(e) => onTextChange(e.target.value)}
          onBlur={onTextBlur}
        />
      </div>
    </div>
  );
}

function ColorRefFieldInput({
  node,
}: {
  node: Extract<FieldNode, { kind: "color_ref" }>;
}) {
  const selectId = fieldDomId(node.name);
  const [value, setValue] = useState(node.value);
  const [swatch, setSwatch] = useState(
    node.palette[node.value] ?? "transparent",
  );

  useEffect(() => {
    setValue(node.value);
    setSwatch(node.palette[node.value] ?? "transparent");
  }, [node.value, node.palette]);

  const onChange = useCallback(
    (next: string, hex: string) => {
      setValue(next);
      setSwatch(hex || "transparent");
    },
    [],
  );

  return (
    <div className="settings-field settings-field--color-ref">
      <label className="settings-field__label" htmlFor={selectId}>
        {node.label}
        <code className="settings-field__path">{node.name}</code>
      </label>
      <div className="color-ref">
        <span
          className="color-ref__swatch"
          style={{ background: swatch }}
          aria-hidden="true"
        />
        <select
          className="input color-ref__select"
          id={selectId}
          name={node.name}
          value={value}
          onChange={(e) => {
            const opt = e.target.selectedOptions[0];
            onChange(e.target.value, opt?.dataset.colorHex ?? "");
          }}
        >
          {node.value && !node.options.includes(node.value) ? (
            <option value={node.value} data-color-hex="">
              {node.value} (missing)
            </option>
          ) : null}
          {node.options.map((opt) => (
            <option key={opt} value={opt} data-color-hex={node.palette[opt] ?? ""}>
              {opt}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}

export default function SettingsField({ node, onBrowsePath }: SettingsFieldProps) {
  if (node.kind === "group") {
    return <RenderGroup node={node} onBrowsePath={onBrowsePath} />;
  }

  const inputId = fieldDomId(node.name);

  switch (node.kind) {
    case "bool":
      return (
        <label className="settings-toggle">
          <input type="hidden" name="__bool__" value={node.name} />
          <input
            type="checkbox"
            className="settings-toggle__input"
            name={node.name}
            value="true"
            defaultChecked={node.value}
          />
          <span className="settings-toggle__label">{node.label}</span>
          <code className="settings-toggle__path">{node.name}</code>
        </label>
      );

    case "int":
    case "float":
      return (
        <div className="settings-field">
          <label className="settings-field__label" htmlFor={inputId}>
            {node.label}
            <code className="settings-field__path">{node.name}</code>
          </label>
          <input
            className="input"
            id={inputId}
            name={node.name}
            type="number"
            step={node.kind === "float" ? "any" : "1"}
            defaultValue={node.value}
          />
        </div>
      );

    case "password":
      return (
        <div className="settings-field">
          <label className="settings-field__label" htmlFor={inputId}>
            {node.label}
            <code className="settings-field__path">{node.name}</code>
          </label>
          <input
            className="input"
            id={inputId}
            name={node.name}
            type="password"
            autoComplete="new-password"
            defaultValue={node.value}
          />
        </div>
      );

    case "select":
      return (
        <div className="settings-field">
          <label className="settings-field__label" htmlFor={inputId}>
            {node.label}
            <code className="settings-field__path">{node.name}</code>
          </label>
          <select className="input" id={inputId} name={node.name} defaultValue={node.value}>
            {node.value && !node.options.includes(node.value) ? (
              <option value={node.value}>{node.value} (current, not configured)</option>
            ) : null}
            {node.options.map((opt) => (
              <option key={opt} value={opt}>
                {opt}
              </option>
            ))}
          </select>
        </div>
      );

    case "color":
      return <ColorFieldInput node={node} />;

    case "color_ref":
      return <ColorRefFieldInput node={node} />;

    case "path":
      return (
        <div className="settings-field settings-field--path">
          <label className="settings-field__label" htmlFor={inputId}>
            {node.label}
            <code className="settings-field__path">{node.name}</code>
          </label>
          <div className="form-row path-input">
            <input
              className="input path-input__text"
              id={inputId}
              name={node.name}
              type="text"
              defaultValue={node.value}
              spellCheck={false}
            />
            <button
              type="button"
              className="btn path-input__browse"
              aria-label={`Browse for ${node.label}`}
              onClick={() => onBrowsePath?.(inputId, node.value)}
            >
              Browse…
            </button>
          </div>
        </div>
      );

    case "multi_choice":
      return (
        <div className="settings-field settings-field--multi">
          <div className="settings-field__label">
            {node.label}
            <code className="settings-field__path">{node.name}</code>
          </div>
          <p className="settings-field__hint">
            Tick a category to keep capturing it. Unticked categories are dropped from
            the live log viewer at capture time.
          </p>
          <input type="hidden" name="__multi__" value={node.name} />
          <div className="multi-choice-grid">
            {node.options.map((opt) => {
              const selected = new Set(node.selected);
              const isOn = selected.has(opt.value.toUpperCase());
              return (
                <label
                  key={`${node.name}-${opt.value}`}
                  className={`multi-choice-grid__item${isOn ? "" : " is-off"}`}
                >
                  <input
                    type="checkbox"
                    name={node.name}
                    value={opt.value}
                    defaultChecked={isOn}
                  />
                  <span className="multi-choice-grid__label">{opt.label}</span>
                </label>
              );
            })}
          </div>
        </div>
      );

    case "list":
      return (
        <div className="settings-field">
          <label className="settings-field__label" htmlFor={inputId}>
            {node.label}
            <code className="settings-field__path">{node.name}</code>
          </label>
          <textarea
            className="textarea settings-list"
            id={inputId}
            name={node.name}
            rows={4}
            spellCheck={false}
            placeholder="One value per line"
            defaultValue={node.value}
          />
          <p className="settings-field__hint">One {node.elem_kind} value per line.</p>
        </div>
      );

    case "json":
      return (
        <div className="settings-field">
          <label className="settings-field__label" htmlFor={inputId}>
            {node.label}
            <code className="settings-field__path">{node.name}</code>
          </label>
          <textarea
            className="textarea settings-json-inline"
            id={inputId}
            name={node.name}
            rows={5}
            spellCheck={false}
            defaultValue={node.value}
          />
          <p className="settings-field__hint">JSON value.</p>
        </div>
      );

    case "str":
    default:
      return (
        <div className="settings-field">
          <label className="settings-field__label" htmlFor={inputId}>
            {node.label}
            <code className="settings-field__path">{node.name}</code>
          </label>
          <input
            className="input"
            id={inputId}
            name={node.name}
            type="text"
            defaultValue={node.value}
          />
        </div>
      );
  }
}
