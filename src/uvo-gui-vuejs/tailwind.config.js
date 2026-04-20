/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{vue,js,ts}'],
  theme: {
    extend: {
      colors: {
        'd-canvas':  '#111217',
        'd-panel':   '#181B1F',
        'd-panel-2': '#22252B',
        'd-border':  '#2C3235',
        'd-hover':   '#202226',
        'd-text':    '#D8D9DA',
        'd-muted':   '#9FA7B3',
        'd-dim':     '#6E7580',

        'l-canvas':  '#E6E8EC',
        'l-panel':   '#F3F5F7',
        'l-panel-2': '#E9ECEF',
        'l-border':  '#C9CED5',
        'l-hover':   '#DEE2E6',
        'l-text':    '#1F2937',
        'l-muted':   '#4A5058',
        'l-dim':     '#828790',

        primary: {
          DEFAULT: '#3274D9',
          600: '#2D65C0',
          400: '#5794F2',
          100: '#C0D6F7',
        },
        good: '#56A64B',
        warn: '#F2CC0C',
        bad:  '#E02F44',
        info: '#8AB8FF',
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', 'sans-serif'],
        mono: ['"JetBrains Mono"', '"SF Mono"', 'Consolas', 'Monaco', 'monospace'],
      },
      fontSize: {
        '2xs': ['10px', '14px'],
        xs: ['11px', '15px'],
        sm: ['12px', '16px'],
        base: ['13px', '18px'],
        lg: ['15px', '22px'],
        xl: ['18px', '24px'],
        '2xl': ['22px', '28px'],
        '3xl': ['28px', '34px'],
      },
      borderRadius: {
        DEFAULT: '2px',
        sm: '2px',
        md: '3px',
        lg: '4px',
      },
      boxShadow: {
        panel: '0 1px 2px rgba(0, 0, 0, 0.06)',
      },
    },
  },
  plugins: [],
}
