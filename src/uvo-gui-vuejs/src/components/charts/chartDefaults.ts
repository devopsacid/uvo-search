import { Chart as ChartJS } from 'chart.js'

export const CHART_COLORS = {
  primary: '#3274D9',
  primaryDim: 'rgba(50, 116, 217, 0.18)',
  primary2: '#5794F2',
  good: '#56A64B',
  warn: '#F2CC0C',
  bad: '#E02F44',
  series: [
    '#3274D9', '#56A64B', '#F2CC0C', '#E02F44',
    '#8AB8FF', '#B877D9', '#E07F14', '#37872D',
  ],
}

function isDark(): boolean {
  return typeof document !== 'undefined' && document.documentElement.classList.contains('dark')
}

export function themedChartColors() {
  const dark = isDark()
  return {
    grid:       dark ? '#2C3235' : '#E4E7EB',
    gridStrong: dark ? '#404449' : '#C3C6CC',
    ticks:      dark ? '#9FA7B3' : '#464C54',
    tooltipBg:  dark ? '#22252B' : '#FFFFFF',
    tooltipFg:  dark ? '#D8D9DA' : '#1F2937',
    tooltipBr:  dark ? '#2C3235' : '#D8DAE0',
  }
}

let applied = false
export function applyChartDefaults() {
  if (applied) return
  applied = true
  ChartJS.defaults.font.family = 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
  ChartJS.defaults.font.size = 11
  ChartJS.defaults.animation = { duration: 250 }
  ChartJS.defaults.plugins.legend.display = false
  ChartJS.defaults.plugins.tooltip.padding = 8
  ChartJS.defaults.plugins.tooltip.borderWidth = 1
  ChartJS.defaults.plugins.tooltip.displayColors = false
}
