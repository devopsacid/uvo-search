import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}

export function formatCurrency(value: number): string {
  return new Intl.NumberFormat('sk-SK', {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: 0,
  }).format(value)
}

export function formatNumber(value: number): string {
  return new Intl.NumberFormat('sk-SK').format(value)
}

export function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`
  const units = ['kB', 'MB', 'GB', 'TB']
  let size = value / 1024
  let unit = 0
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024
    unit++
  }
  return `${new Intl.NumberFormat('sk-SK', {
    minimumFractionDigits: size < 10 ? 1 : 0,
    maximumFractionDigits: size < 10 ? 1 : 0,
  }).format(size)} ${units[unit]}`
}
