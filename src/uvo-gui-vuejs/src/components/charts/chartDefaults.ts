import { Chart as ChartJS } from 'chart.js'

export const TERM = {
  accent: '#ff9e1f',
  accentDim: 'rgba(255,158,31,0.18)',
  grid: '#2a2d30',
  ticks: '#8a8e92',
  up: '#3fb950',
  down: '#f85149',
  bg: '#0b0d0f',
  font: '"JetBrains Mono", "SF Mono", Consolas, monospace',
}

let applied = false

export function applyTerminalChartDefaults() {
  if (applied) return
  applied = true
  ChartJS.defaults.color = TERM.ticks
  ChartJS.defaults.font.family = TERM.font
  ChartJS.defaults.font.size = 10
  ChartJS.defaults.borderColor = TERM.grid
  ChartJS.defaults.animation = false
  ChartJS.defaults.plugins.legend.display = false
  ChartJS.defaults.plugins.tooltip.backgroundColor = '#141618'
  ChartJS.defaults.plugins.tooltip.borderColor = TERM.grid
  ChartJS.defaults.plugins.tooltip.borderWidth = 1
  ChartJS.defaults.plugins.tooltip.titleColor = TERM.accent
  ChartJS.defaults.plugins.tooltip.bodyColor = '#d6d7d4'
  ChartJS.defaults.plugins.tooltip.titleFont = { family: TERM.font, size: 10, weight: 'bold' }
  ChartJS.defaults.plugins.tooltip.bodyFont = { family: TERM.font, size: 10, weight: 'normal' }
  ChartJS.defaults.plugins.tooltip.padding = 6
  ChartJS.defaults.plugins.tooltip.displayColors = false
}
