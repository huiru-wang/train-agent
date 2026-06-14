"use client";

import { useState } from "react";
import { Check, ChevronDown, Send, X } from "lucide-react";

interface FormField {
  name: string;
  label: string;
  type: "text" | "select" | "multiselect";
  options?: string[];
  required?: boolean;
}

interface ClarifyFormProps {
  title: string;
  description: string;
  fields: FormField[];
  onSubmit: (values: Record<string, string | string[]>) => void;
}

export function ClarifyForm({
  title,
  description,
  fields,
  onSubmit,
}: ClarifyFormProps) {
  const [values, setValues] = useState<Record<string, string | string[]>>({});
  const [submitted, setSubmitted] = useState(false);
  const [cancelled, setCancelled] = useState(false);

  if (submitted) {
    return (
      <div className="rounded-xl border border-border bg-muted/30 px-4 py-3">
        <p className="text-xs text-muted-foreground">✓ 已提交表单: {title}</p>
      </div>
    );
  }

  if (cancelled) {
    return (
      <div className="rounded-xl border border-border bg-muted/30 px-4 py-3">
        <p className="text-xs text-muted-foreground">✗ 已取消: {title}</p>
      </div>
    );
  }

  const handleChange = (name: string, value: string | string[]) => {
    setValues((prev) => ({ ...prev, [name]: value }));
  };

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    setSubmitted(true);
    onSubmit(values);
  };

  const handleCancel = () => {
    setCancelled(true);
    onSubmit({ __cancelled__: "true" });
  };

  const isValid = fields
    .filter((field) => field.required !== false)
    .every((field) => {
      const fieldValue = values[field.name];
      if (Array.isArray(fieldValue)) return fieldValue.length > 0;
      return fieldValue && fieldValue.trim().length > 0;
    });

  return (
    <div className="rounded-xl border border-accent/30 bg-accent/5 p-4">
      <h4 className="mb-1 text-sm font-medium text-foreground">{title}</h4>
      <p className="mb-4 text-xs text-muted-foreground">{description}</p>

      <form onSubmit={handleSubmit} className="flex flex-col gap-3">
        {fields.map((field) => (
          <FormFieldComponent
            key={field.name}
            field={field}
            value={values[field.name]}
            onChange={(value) => handleChange(field.name, value)}
          />
        ))}

        <div className="mt-1 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={handleCancel}
            className="flex items-center justify-center gap-1.5 rounded-lg border border-border px-4 py-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted/50"
          >
            <X size={12} />
            取消
          </button>
          <button
            type="submit"
            disabled={!isValid}
            className="flex items-center justify-center gap-1.5 rounded-lg bg-accent px-4 py-2 text-xs font-medium text-accent-foreground transition-colors hover:bg-accent/90 disabled:opacity-40"
          >
            <Send size={12} />
            提交
          </button>
        </div>
      </form>
    </div>
  );
}

interface FormFieldComponentProps {
  field: FormField;
  value: string | string[] | undefined;
  onChange: (value: string | string[]) => void;
}

function FormFieldComponent({
  field,
  value,
  onChange,
}: FormFieldComponentProps) {
  const [isOpen, setIsOpen] = useState(false);
  const labelElement = (
    <label className="mb-1 block text-xs font-medium text-foreground/80">
      {field.label}
      {field.required !== false && (
        <span className="ml-0.5 text-accent">*</span>
      )}
    </label>
  );

  if (field.type === "text") {
    return (
      <div>
        {labelElement}
        <input
          value={(value as string) ?? ""}
          onChange={(event) => onChange(event.target.value)}
          className="w-full rounded-lg border border-border bg-muted px-3 py-2 text-xs text-foreground placeholder:text-muted-foreground focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
          placeholder={`请输入${field.label}`}
        />
      </div>
    );
  }

  if (field.type === "select") {
    const selectedValue = (value as string) ?? "";
    const options = field.options ?? [];

    return (
      <div>
        {labelElement}
        <button
          type="button"
          onClick={() => setIsOpen((open) => !open)}
          disabled={options.length === 0}
          className="flex w-full items-center justify-between gap-2 rounded-lg border border-border bg-muted px-3 py-2 text-left text-xs text-foreground transition-colors hover:border-accent/50 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent disabled:cursor-not-allowed disabled:opacity-60"
        >
          <span className={selectedValue ? "" : "text-muted-foreground"}>
            {selectedValue || "请选择"}
          </span>
          <ChevronDown
            size={14}
            className={`shrink-0 text-muted-foreground transition-transform ${
              isOpen ? "rotate-180" : ""
            }`}
          />
        </button>
        {isOpen && (
          <div className="mt-1 max-h-48 overflow-y-auto rounded-lg border border-border bg-muted p-1">
            {options.map((option) => {
              const isSelected = selectedValue === option;
              return (
                <button
                  key={option}
                  type="button"
                  onClick={() => {
                    onChange(option);
                    setIsOpen(false);
                  }}
                  className={`flex w-full items-center justify-between gap-2 rounded-md px-2.5 py-1.5 text-left text-xs transition-colors ${
                    isSelected
                      ? "bg-accent/20 text-accent"
                      : "text-foreground hover:bg-background/60"
                  }`}
                >
                  <span>{option}</span>
                  {isSelected && <Check size={12} className="shrink-0" />}
                </button>
              );
            })}
          </div>
        )}
      </div>
    );
  }

  if (field.type === "multiselect") {
    const selectedValues = (value as string[]) ?? [];
    return (
      <div>
        {labelElement}
        <div className="flex flex-wrap gap-1.5">
          {field.options?.map((option) => {
            const isSelected = selectedValues.includes(option);
            return (
              <button
                key={option}
                type="button"
                onClick={() => {
                  const newValues = isSelected
                    ? selectedValues.filter((selectedValue) => selectedValue !== option)
                    : [...selectedValues, option];
                  onChange(newValues);
                }}
                className={`rounded-md border px-2.5 py-1 text-xs transition-colors ${
                  isSelected
                    ? "border-accent bg-accent/20 text-accent"
                    : "border-border bg-muted text-muted-foreground hover:border-accent/40"
                }`}
              >
                {option}
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  return null;
}
