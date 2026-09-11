import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatInr(amount: number): string {
  const sign = amount < 0 ? "-" : "";
  const digits = String(Math.abs(Math.round(amount)));
  if (digits.length <= 3) return `${sign}₹${digits}`;
  let result = digits.slice(-3);
  let rest = digits.slice(0, -3);
  while (rest.length) {
    result = `${rest.slice(-2)},${result}`;
    rest = rest.slice(0, -2);
  }
  return `${sign}₹${result}`;
}
