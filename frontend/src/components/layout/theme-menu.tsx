"use client";

import { Button, Dropdown, Label, useIsHydrated } from "@heroui/react";
import { Monitor, Moon, Sun, SunMoon } from "lucide-react";
import { useTheme } from "next-themes";

export function ThemeMenu() {
  const { theme, setTheme } = useTheme();
  const hydrated = useIsHydrated();
  return (
    <Dropdown>
      <Button variant="ghost" isIconOnly aria-label="Changer de thème"><SunMoon size={19} /></Button>
      <Dropdown.Popover placement="bottom end">
        <Dropdown.Menu aria-label="Apparence" selectionMode="single"
          selectedKeys={hydrated && theme ? [theme] : []} onAction={key => setTheme(String(key))}>
          <Dropdown.Item id="light" textValue="Clair"><Sun size={16} /><Label>Clair</Label><Dropdown.ItemIndicator /></Dropdown.Item>
          <Dropdown.Item id="dark" textValue="Sombre"><Moon size={16} /><Label>Sombre</Label><Dropdown.ItemIndicator /></Dropdown.Item>
          <Dropdown.Item id="system" textValue="Système"><Monitor size={16} /><Label>Système</Label><Dropdown.ItemIndicator /></Dropdown.Item>
        </Dropdown.Menu>
      </Dropdown.Popover>
    </Dropdown>
  );
}
