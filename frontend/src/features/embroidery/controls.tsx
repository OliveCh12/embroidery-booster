"use client";

import { FieldError, Label, ListBox, NumberField, Select, Switch } from "@heroui/react";

export function NumberSetting({ label, value, onChange, min, max, step = 1, optional = false, disabled = false }: {
  label: string; value: number | null; onChange: (value: number | null) => void;
  min: number; max: number; step?: number; optional?: boolean; disabled?: boolean;
}) {
  return (
    <NumberField value={value ?? NaN} onChange={value => onChange(Number.isNaN(value) ? null : value)}
      minValue={min} maxValue={max} step={step} isRequired={!optional} isDisabled={disabled}
      formatOptions={{ maximumFractionDigits: 3, useGrouping: false }} fullWidth variant="secondary">
      <Label>{label}</Label>
      <NumberField.Group><NumberField.Input placeholder={optional ? "Auto" : undefined} /></NumberField.Group>
      <FieldError />
    </NumberField>
  );
}

export function ChoiceSetting<V extends string>({ label, value, onChange, options, disabled = false }: {
  label: string; value: V; onChange: (value: V) => void;
  options: readonly { value: V; label: string }[]; disabled?: boolean;
}) {
  return (
    <Select value={value} onChange={key => { if (typeof key === "string") onChange(key as V); }}
      isDisabled={disabled} fullWidth variant="secondary">
      <Label>{label}</Label>
      <Select.Trigger><Select.Value /><Select.Indicator /></Select.Trigger>
      <Select.Popover>
        <ListBox items={options}>
          {option => <ListBox.Item id={option.value} textValue={option.label}><Label>{option.label}</Label><ListBox.ItemIndicator /></ListBox.Item>}
        </ListBox>
      </Select.Popover>
    </Select>
  );
}

export function ToggleSetting({ label, value, onChange, disabled = false }: {
  label: string; value: boolean; onChange: (value: boolean) => void; disabled?: boolean;
}) {
  return (
    <Switch size="sm" isSelected={value} onChange={onChange} isDisabled={disabled} className="justify-between">
      <Switch.Content><Label className="text-sm">{label}</Label></Switch.Content>
      <Switch.Control><Switch.Thumb /></Switch.Control>
    </Switch>
  );
}
