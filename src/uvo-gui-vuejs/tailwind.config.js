/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js,ts}'],
  theme: {
    extend: {
      colors: {
        ink: {
          950: '#0b0d0f',
          900: '#0f1113',
          800: '#141618',
          700: '#1d1f22',
          600: '#2a2d30',
          500: '#3a3d40',
        },
        fg: {
          primary: '#d6d7d4',
          muted: '#8a8e92',
          dim: '#6a6e72',
        },
        accent: {
          DEFAULT: '#ff9e1f',
          dim: '#b36e10',
          glow: 'rgba(255,158,31,0.12)',
        },
        up: '#3fb950',
        down: '#f85149',
      },
      fontFamily: {
        mono: ['"JetBrains Mono"', '"SF Mono"', 'Consolas', 'Monaco', 'monospace'],
        sans: ['"JetBrains Mono"', '"SF Mono"', 'Consolas', 'Monaco', 'monospace'],
      },
      fontSize: {
        '2xs': ['10px', '14px'],
        xs: ['11px', '15px'],
        sm: ['12px', '16px'],
        base: ['13px', '18px'],
        lg: ['15px', '20px'],
        xl: ['18px', '22px'],
        '2xl': ['22px', '26px'],
        '3xl': ['28px', '32px'],
      },
      letterSpacing: {
        tightest: '-0.02em',
        wider: '0.08em',
        widest: '0.14em',
      },
      borderRadius: {
        DEFAULT: '0',
        none: '0',
        sm: '0',
        md: '0',
        lg: '0',
        xl: '0',
        full: '9999px',
      },
    },
  },
  plugins: [],
}
